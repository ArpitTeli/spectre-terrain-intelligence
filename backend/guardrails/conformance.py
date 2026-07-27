"""Conformance suite for the Guardrail Kernel.

Run it:   python -m guardrails.conformance         (from the repo root, F:\\datasetSamples)

Four things it proves:
  1. GOLDEN   — each check fires (and stays silent) exactly when it should.
  2. PARITY   — the offline and online adapters read the *same* Report: a clean
                order is accepted+allowed, a geometry/doctrine error is
                rejected+blocked, a warning-only order is flagged+allowed. This
                is the train/serve parity guarantee, mechanised.
  3. DRIFT    — the vendored policy tables equal the repo-root doctrine.py /
                threat.py, so the self-contained copy can't silently diverge.
  4. SWEEP    — runs the kernel across the real dataset (spectre_dataset.json)
                and prints a finding histogram so regressions in the data show up.

Exits non-zero if any assertion fails.
"""

import json
import os
import sys

from . import policy, kernel
from .adapters import offline_decision, online_decision


# --------------------------------------------------------------------------- #
# Builders — keep golden fixtures doctrine-clean except for the defect on trial.
# --------------------------------------------------------------------------- #
def contact(cid, ctype, pos, confidence=0.8):
    return {
        "contact_id": cid,
        "type": ctype,
        "pos": list(pos),
        "confidence": confidence,
        "engagement_radius": policy.ENGAGEMENT_RADII[ctype],
        "vulnerable_unit_types": policy.vulnerable_types_for(ctype),
    }


def unit(uid, utype, pos):
    return {"unit_id": uid, "type": utype, "pos": list(pos), "status": "ready"}


def reasoning(text="Neutral assessment of the situation with enough length to pass."):
    pad = " Padded to clear the forty character minimum for each reasoning key."
    return {k: (text + pad) for k in policy.REASONING_KEYS}


def order(uid, intent, target, anchors, engage=None, avoid=None,
          prefer_surface=None, rtext=None):
    cons = {"prefer_surface": prefer_surface}
    if engage is not None:
        cons["engage_zones"] = engage
    if avoid is not None:
        cons["avoid_zones"] = avoid
    return {
        "unit_id": uid, "intent": intent, "target": list(target),
        "anchors": [list(a) for a in anchors], "constraints": cons,
        "reasoning": reasoning() if rtext is None else {k: rtext for k in policy.REASONING_KEYS},
    }


def state(contacts, units, threat_level=None):
    s = {"known_contacts": contacts, "friendly_units": units, "objective": "attack"}
    s["threat_level"] = threat_level if threat_level else policy.classify_threat(contacts)
    return s


# --------------------------------------------------------------------------- #
# GOLDEN cases: (name, state, orders, expected_error_codes, expected_warn_codes)
# --------------------------------------------------------------------------- #
def golden_cases():
    cases = []

    # A: clean standoff — MBT engages IFV from reach, never enters the box.
    cA = contact("enemy_0", "ifv", (4000, 4000))
    cases.append((
        "clean_standoff",
        state([cA], [unit("friendly_0", "mbt", (2000, 2000))], "high"),
        [order("friendly_0", "attack", (3200, 3200), [(2500, 2500), (3000, 3000)],
               engage=[{"pos": [4000, 4000], "radius": 250, "target_contact": "enemy_0"}])],
        set(), set(),
    ))

    # B: engage unreachable — MBT declares engaging an APC 2.8km away.
    cB = contact("enemy_0", "apc", (6000, 6000))
    cases.append((
        "engage_unreachable",
        state([cB], [unit("friendly_0", "mbt", (1500, 1500))], None),
        [order("friendly_0", "attack", (4000, 4000),
               [(2000, 2000), (3000, 3000), (4000, 4000)],
               engage=[{"pos": [6000, 6000], "radius": 250, "target_contact": "enemy_0"}])],
        {"ENGAGE_UNREACHABLE"}, set(),
    ))

    # C: doctrine mismatch — infantry ordered to engage an MRAP.
    cC = contact("enemy_0", "mrap", (3000, 3000))
    cases.append((
        "doctrine_mismatch",
        state([cC], [unit("friendly_0", "infantry", (2800, 2900))], None),
        [order("friendly_0", "attack", (2950, 2950), [(2850, 2900), (2950, 2950)],
               engage=[{"pos": [3000, 3000], "radius": 250, "target_contact": "enemy_0"}])],
        {"ENGAGE_MISMATCH"}, set(),
    ))

    # D: avoid entered — route crosses a declared no-entry zone.
    cD = contact("enemy_0", "mbt", (6500, 6500))
    cases.append((
        "avoid_entered",
        state([cD], [unit("friendly_0", "mbt", (1500, 1500))], "high"),
        [order("friendly_0", "move", (4000, 4000), [(2500, 2500), (3500, 3500)],
               avoid=[{"pos": [3000, 3000], "radius": 250}],
               rtext="Advance to the objective. Enemy mbt threat noted to the northeast.")],
        {"AVOID_ENTERED"}, set(),
    ))

    # E: contradiction — engaged contact sits inside the order's own avoid_zone.
    cE = contact("enemy_0", "apc", (3000, 3000))
    cases.append((
        "engage_target_in_avoid",
        state([cE], [unit("friendly_0", "mbt", (2000, 2000))], None),
        [order("friendly_0", "attack", (2950, 2950), [(2500, 2500), (2900, 2900)],
               engage=[{"pos": [3000, 3000], "radius": 250, "target_contact": "enemy_0"}],
               avoid=[{"pos": [3000, 3000], "radius": 250}])],
        {"ENGAGE_TARGET_IN_AVOID", "AVOID_ENTERED"}, set(),
    ))

    # F: coordinate out of range (contact off-route so nothing else fires).
    cF = contact("enemy_0", "ifv", (1500, 4000))
    cases.append((
        "coord_oor",
        state([cF], [unit("friendly_0", "mbt", (2000, 2000))], "high"),
        [order("friendly_0", "attack", (9000, 9000), [(2500, 2500), (3000, 3000)])],
        {"COORD_OOR"}, set(),
    ))

    # G: clean close-assault within reach slack — infantry ambush on a truck.
    cG = contact("enemy_0", "truck", (3000, 3000))
    cases.append((
        "clean_close_assault_slack",
        state([cG], [unit("friendly_0", "infantry", (2600, 2600))], None),
        [order("friendly_0", "attack", (2760, 2760), [(2680, 2680), (2760, 2760)],
               engage=[{"pos": [3000, 3000], "radius": 250, "target_contact": "enemy_0"}])],
        set(), set(),
    ))

    # H: warning-only — order clean but threat_level mislabelled.
    cH = contact("enemy_0", "ifv", (4000, 4000))
    cases.append((
        "warn_only_threat_mislabel",
        state([cH], [unit("friendly_0", "mbt", (2000, 2000))], "low"),  # should be high
        [order("friendly_0", "attack", (3200, 3200), [(2500, 2500), (3000, 3000)],
               engage=[{"pos": [4000, 4000], "radius": 250, "target_contact": "enemy_0"}])],
        set(), {"THREAT_MISCLASSIFIED"},
    ))

    # I: engage box not centred on its target (WARN), engagement still reachable.
    cI = contact("enemy_0", "ifv", (4000, 4000))
    cases.append((
        "engage_zone_offset",
        state([cI], [unit("friendly_0", "mbt", (2000, 2000))], "high"),
        [order("friendly_0", "attack", (3400, 3400), [(2600, 2600), (3400, 3400)],
               engage=[{"pos": [3600, 3600], "radius": 200, "target_contact": "enemy_0"}])],
        set(), {"ENGAGE_ZONE_NOT_ON_CONTACT"},
    ))

    return cases


def run_golden():
    failures = []
    for name, st, orders, want_err, want_warn in golden_cases():
        rep = kernel.evaluate(st, orders)
        got_err = {f.code for f in rep.errors}
        got_warn = {f.code for f in rep.warnings}
        if got_err != want_err or got_warn != want_warn:
            failures.append(
                f"  [{name}] err {sorted(got_err)} (want {sorted(want_err)}), "
                f"warn {sorted(got_warn)} (want {sorted(want_warn)})"
            )
    return failures


# --------------------------------------------------------------------------- #
# PARITY: the two adapters must agree on the shared verdict.
# --------------------------------------------------------------------------- #
def run_parity():
    failures = []
    cases = {name: (st, orders) for name, st, orders, *_ in golden_cases()}

    def check(name, off_status, on_action):
        st, orders = cases[name]
        rep = kernel.evaluate(st, orders)
        off = offline_decision(rep)
        on = online_decision(rep)
        if off.status != off_status:
            failures.append(f"  [{name}] offline={off.status} want {off_status}")
        if on.action != on_action:
            failures.append(f"  [{name}] online={on.action} want {on_action}")

    check("clean_standoff", "accept", "allow")
    check("engage_unreachable", "reject", "block")     # geometry error
    check("doctrine_mismatch", "reject", "block")      # doctrine error
    check("coord_oor", "reject", "block")              # schema error (unexecutable)
    check("warn_only_threat_mislabel", "flag", "allow")  # warn only
    check("engage_zone_offset", "flag", "allow")       # warn only
    return failures


# --------------------------------------------------------------------------- #
# DRIFT: vendored policy == repo-root doctrine.py / threat.py.
# --------------------------------------------------------------------------- #
def run_drift():
    failures = []
    try:
        import doctrine as legacy_doctrine
        import threat as legacy_threat
    except ImportError:
        # No legacy modules in this deployment (e.g. the pipeline repo, where
        # policy.py is the sole source of the doctrine/threat tables). There is
        # nothing to drift against, so the check is not applicable — skip rather
        # than fail. Signalled to main() by returning None.
        return None

    if policy.VULNERABLE_TO != legacy_doctrine.VULNERABLE_TO:
        failures.append("  VULNERABLE_TO drifted from doctrine.py")
    if policy.THREAT_POINTS != legacy_threat.THREAT_POINTS:
        failures.append("  THREAT_POINTS drifted from threat.py")
    if tuple(policy.FORCES_HIGH) != tuple(legacy_threat.FORCES_HIGH):
        failures.append("  FORCES_HIGH drifted from threat.py")

    # Classification must agree across a spread of forces.
    probes = [
        [], [{"type": "infantry"}], [{"type": "light"}, {"type": "infantry"}],
        [{"type": "apc"}, {"type": "mrap"}, {"type": "light"}],
        [{"type": "mbt"}], [{"type": "ifv"}, {"type": "apc"}],
        [{"type": "apc"}], [{"type": "apc"}, {"type": "apc"}],
    ]
    for p in probes:
        if p and policy.classify_threat(p) != legacy_threat.classify(p):
            failures.append(f"  classify disagreement on {[c['type'] for c in p]}")
    return failures


# --------------------------------------------------------------------------- #
# SWEEP: run the kernel over the real dataset and histogram the findings.
# --------------------------------------------------------------------------- #
def run_sweep():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "spectre_dataset.json")
    if not os.path.exists(path):
        print(f"  (no dataset at {path}; skipping sweep)")
        return
    data = json.load(open(path, encoding="utf-8"))

    from collections import Counter
    err_hist, warn_hist = Counter(), Counter()
    rejected = flagged = accepted = 0
    for ex in data:
        rep = kernel.evaluate_example(ex)
        for f in rep.errors:
            err_hist[f.code] += 1
        for f in rep.warnings:
            warn_hist[f.code] += 1
        d = offline_decision(rep).status
        rejected += d == "reject"
        flagged += d == "flag"
        accepted += d == "accept"

    print(f"  dataset examples: {len(data)}")
    print(f"  offline verdicts: accept={accepted}  flag={flagged}  reject={rejected}")
    print(f"  ERROR findings:   {dict(err_hist) or 'none'}")
    print(f"  WARN findings:    {dict(warn_hist) or 'none'}")


# --------------------------------------------------------------------------- #
def main():
    print(f"SPECTRE Guardrail conformance — policy {policy.POLICY_VERSION}\n")
    all_fail = []

    for label, fn in [("GOLDEN", run_golden), ("PARITY", run_parity),
                      ("DRIFT", run_drift)]:
        fails = fn()
        if fails is None:                       # check not applicable here
            print(f"[SKIP] {label} (legacy doctrine.py/threat.py not present; "
                  f"policy.py is the sole source)")
            continue
        status = "PASS" if not fails else f"FAIL ({len(fails)})"
        print(f"[{status}] {label}")
        for line in fails:
            print(line)
        all_fail.extend(fails)

    print("\n[SWEEP] dataset")
    run_sweep()

    print()
    if all_fail:
        print(f"CONFORMANCE FAILED — {len(all_fail)} assertion(s)")
        return 1
    print("CONFORMANCE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
