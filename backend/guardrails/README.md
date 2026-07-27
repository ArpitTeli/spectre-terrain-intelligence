# SPECTRE Guardrail Kernel

A single, versioned coherence layer shared by the offline synthetic-data pipeline
and the deployed edge Tasking Layer. The same logic that rejects a bad training
example is the logic that blocks a bad live command — the model is never taught
an order its runtime would refuse.

---

## Architecture

```
guardrails/
  policy.py          — versioned constants (single source of truth)
  policy.json        — exported policy for cross-runtime parity (JS/edge)
  geo.py             — pure 2-D geometry, no dependencies
  kernel.py          — evaluate(state, orders) -> Report
  adapters.py        — offline_decision / online_decision
  geo_filter.py      — drop-in pipeline Stage-4 replacement
  edge_guardrail.js  — JS mirror for the Electron Tasking Layer
  conformance.py     — golden cases, parity, drift, dataset sweep
```

### Policy (`policy.py` / `policy.json`)

All numeric thresholds, enumerations, and doctrine tables live here and nowhere
else. `policy.as_dict()` writes `policy.json`; the JS edge module loads that
file at startup. Changing a number in `policy.py` and re-exporting the JSON is
the only step needed to update both sides simultaneously.

Key tables:

| Table | Purpose |
|---|---|
| `ENGAGEMENT_RADII` | Enemy weapon reach by type — used to annotate contacts |
| `FRIENDLY_REACH` | Friendly weapon reach by type — the reachability predicate |
| `REACH_SLACK` | 60 m tolerance for standoff-vs-close-assault boundary |
| `THREAT_POINTS` / `FORCES_HIGH` | Capability-weighted threat classification |
| `VULNERABLE_TO` | Doctrine matrix — which unit types are outmatched by which contacts |
| `NON_ENGAGING_TYPES` | Support/transport platforms that should never carry an engage_zone |

### Kernel (`kernel.py`)

`evaluate(state, orders) -> Report` is the only public entry point. It is:

- **Pure** — no I/O, no randomness, no side effects.
- **Deterministic** — same inputs always produce the same Report.
- **Dependency-free** — only `geo` and `policy` from this package.

Finding severities and categories:

| Severity | Meaning |
|---|---|
| `ERROR` | The order is physically or doctrinally unexecutable — must not train on, must not send |
| `WARN` | Plausible but worth review — flags for the judge stage offline; advisory at the edge |

| Category | Checks |
|---|---|
| `SCHEMA` | Coordinate bounds, unresolved target_contact, threat-level parity |
| `DOCTRINE` | Engage-mismatch (outmatched unit), non-engaging type with engage_zone |
| `GEOMETRY` | Route enters avoid_zone, engage unreachable, engaged target inside avoid_zone, zone offset |
| `REASONING` | Unacknowledged threat transit, avoidance-claim contradiction |

#### The reachability predicate

The old geo_filter checked whether the route *entered* the engage_zone box.
That was wrong for standoff platforms (MBT, IFV) which engage from range and
should never enter the box. The kernel instead asks:

> Does the route's closest approach to the contact ever come within
> `FRIENDLY_REACH[unit_type] + REACH_SLACK` metres?

A standoff MBT (reach 1200 m) satisfies this from a waypoint 1100 m away.
An infantry unit (reach 300 m) must actually close to within 360 m.
`ENGAGE_UNREACHABLE` (ERROR/GEOMETRY) fires when the answer is no.

### Adapters (`adapters.py`)

The kernel decides *what is wrong*. The adapters decide *what to do about it*.

**Offline** (`offline_decision`):

| Report state | Verdict | Action |
|---|---|---|
| Any ERROR | `reject` | Drop — regenerate, never hand-patch |
| WARN only | `flag` | Pass to dual-judge / human review |
| Clean | `accept` | Merge into dataset |

**Online** (`online_decision`):

| Report state | Action |
|---|---|
| ERROR in GEOMETRY / DOCTRINE / SCHEMA | `block` — fall back to `HOLD` (or caller-supplied fallback) |
| WARN only, or REASONING ERROR | `allow` — surface advisories to operator |
| Clean | `allow` |

REASONING errors are advisory at the edge because a heuristic text check
should never halt a live unit; it is a training-data quality signal, not a
safety gate.

### Train/serve parity guarantee

`conformance.py::run_parity()` mechanises this guarantee. It takes the same
nine golden cases through both adapters and asserts:

- A clean order is `accept` offline and `allow` online.
- A geometry/doctrine/schema ERROR is `reject` offline and `block` online.
- A WARN-only order is `flag` offline and `allow` online.

The conformance suite exits non-zero on any failure, so it can run in CI.

---

## Integration

### Offline pipeline (Python)

`geo_filter.py` is a drop-in replacement for `backend/pipeline/geo_filter.py`.
It exposes the same public API:

```python
validate_example(example, raw_grid=None) -> {"passed", "status", "flags", "flag_count", "policy_version"}
run_geo_filter(batch_size=None)          -> (passed, failed)
```

`passed` is `True` when there are no ERROR findings (WARN-only passes geo;
the judge stage sees the warnings). `status` is the offline adapter verdict
(`accept` / `flag` / `reject`).

Installation: copy `guardrails/` into `backend/` (or add to `PYTHONPATH`),
then replace the body of `backend/pipeline/geo_filter.py` with:

```python
from guardrails.geo_filter import validate_example, run_geo_filter
```

### Dataset validator (`validate.py`)

`validate.py` runs the kernel after its own per-field schema checks:

```python
rep = kernel.evaluate(sj, orders)
for f in rep.errors:
    errs.append(f'{tag} {f.code} [{f.category}] {f.message}')
```

This means a batch that passes all field-level checks but contains a route that
enters its own avoid_zone, or a unit that can never reach its declared target,
is still rejected before merging into `spectre_dataset.json`.

### Edge / Electron (`edge_guardrail.js`)

Load in `electron/main.js` immediately before writing to the Arma bridge:

```js
const { evaluate, onlineDecision } = require('./guardrails/edge_guardrail');

// state = live tracked units + contacts from the Tasking Layer
const report  = evaluate(state, orders);
const decision = onlineDecision(report, 'HOLD');

if (!decision.allowed) {
  holdUnit(order.unit_id, decision);   // log reason, do not send
  return;
}
// safe to write to spectre_cmds.sqf via callExtension
```

`edge_guardrail.js` loads `policy.json` at `require` time — no network, no
Python runtime. It mirrors every geometry and doctrine check from `kernel.py`
using the same numbers from the shared JSON.

---

## Running the conformance suite

```bash
# from F:\datasetSamples
python -m guardrails.conformance
```

Expected output:

```
[PASS] GOLDEN
[PASS] PARITY
[PASS] DRIFT
[SWEEP] dataset
  ...
CONFORMANCE PASSED
```

DRIFT compares the vendored `policy.py` tables against the repo-root
`doctrine.py` and `threat.py`. If those files change, conformance fails until
`policy.py` is updated and `policy.json` is re-exported.

---

## Inspecting the dataset

```bash
python check_dataset.py                # summary + all examples with findings
python check_dataset.py --errors-only  # suppress warnings
python check_dataset.py --index 4      # single example
```

The current 50-example dataset has 26 rejects (hard geometry errors), 15 flags
(warnings), and 9 clean accepts. The dominant errors are `AVOID_ENTERED` (23)
and `ENGAGE_TARGET_IN_AVOID` (12) — the teacher model was placing avoid_zones
that its own routes crossed, and engage targets inside those zones. These
examples must be regenerated before the dataset is used for training.

---

## Updating policy

1. Edit constants in `guardrails/policy.py`.
2. Re-export: `python -c "import json; from guardrails.policy import as_dict; json.dump(as_dict(), open('guardrails/policy.json','w'), indent=2)"`.
3. Mirror any numeric change in `edge_guardrail.js` (the JS reads `policy.json`
   at runtime, so table values are automatic; only structural logic changes need
   a code edit).
4. Run `python -m guardrails.conformance` — fix any golden case that now fails.
