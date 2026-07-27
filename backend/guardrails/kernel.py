"""SPECTRE Guardrail Kernel — the pure, deterministic coherence core.

One function, ``evaluate(state, orders)``, returns a :class:`Report` of findings.
It is the single body of logic shared by:

  * **offline** synthetic-data generation — reject/flag teacher output before it
    becomes a training example (see ``adapters.offline_decision`` and the
    drop-in ``geo_filter`` for the pipeline), and
  * **online** edge command issuance — gate the deployed Tasking Layer model's
    order before it reaches the Arma bridge (see ``adapters.online_decision``).

Because the *same* kernel runs on both sides against the *same* :mod:`policy`
constants, a training example the kernel rejects is an order the edge would also
refuse — the model is never taught a policy its runtime forbids (train/serve
parity).

Scope: the kernel owns *coherence* — the checks that must agree across train and
serve (doctrine suitability, engagement reachability, avoid-zone entry,
engage/avoid contradiction, threat-classification parity, reasoning-vs-geometry
consistency) plus the minimal schema sanity those checks depend on. Exhaustive
dataset schema validation stays in ``validate.py``, which calls this kernel for
the coherence layer.

No I/O, no network, no dependencies beyond :mod:`geo` and :mod:`policy`.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from . import policy
from . import geo


# --------------------------------------------------------------------------- #
# Finding / Report
# --------------------------------------------------------------------------- #
ERROR = "error"
WARN = "warn"

# Categories let adapters reason about *kinds* of problems without hard-coding
# every code. "geometry" and "doctrine" errors are physically/tactically unsafe;
# "schema" is data hygiene; "reasoning" is heuristic text-vs-geometry mismatch.
SCHEMA = "schema"
DOCTRINE = "doctrine"
GEOMETRY = "geometry"
REASONING = "reasoning"


@dataclass
class Finding:
    code: str
    severity: str          # ERROR | WARN
    category: str          # SCHEMA | DOCTRINE | GEOMETRY | REASONING
    message: str
    unit_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class Report:
    policy_version: str
    findings: List[Finding] = field(default_factory=list)

    def add(self, code, severity, category, message, unit_id=None, **data):
        self.findings.append(
            Finding(code, severity, category, message, unit_id, data)
        )

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self):
        return [f for f in self.findings if f.severity == WARN]

    @property
    def ok(self):
        """True when there are no ERROR findings (WARNs allowed)."""
        return not self.errors

    @property
    def clean(self):
        """True when there are no findings at all."""
        return not self.findings

    def to_dict(self):
        return {
            "policy_version": self.policy_version,
            "ok": self.ok,
            "clean": self.clean,
            "error_count": len(self.errors),
            "warn_count": len(self.warnings),
            "findings": [f.to_dict() for f in self.findings],
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _reasoning_text(order):
    r = order.get("reasoning")
    if isinstance(r, dict):
        return " ".join(str(v) for v in r.values()).lower()
    return str(r or "").lower()


# Narrow, high-signal standoff phrases only. Deliberately excludes bare "avoid"
# / "beyond" / "outside" — those match routine avoid_zone prose and a legitimate
# target that sits inside a threat radius (you are *attacking* it). This check
# fires only when the reasoning makes an explicit out-of-range claim that the
# destination geometry contradicts — the DeepSeek "outside the SAM radius" error.
_AVOIDANCE_PHRASES = (
    "out of range", "outside engagement", "outside the engagement",
    "outside its engagement", "outside weapon", "outside the weapon",
    "out of reach", "outside its reach", "beyond weapon", "beyond its reach",
    "standoff", "stand off", "safe distance", "stay clear of", "clear of the",
    "out of its range", "outside the threat", "outside the reach",
)


def _route(order, unit_pos):
    """Canonical route for an order: start pos (if known) -> anchors -> target.

    Consecutive duplicate points are collapsed so degenerate zero-length
    segments don't skew closest-approach maths.
    """
    pts = []
    if unit_pos is not None:
        pts.append(list(unit_pos))
    pts.extend([list(a) for a in order.get("anchors", [])])
    tgt = order.get("target")
    if tgt is not None:
        pts.append(list(tgt))
    out = []
    for p in pts:
        if not out or out[-1] != p:
            out.append(p)
    return out


def _in_bounds(p):
    return (policy.COORD_MIN <= p[0] <= policy.COORD_MAX
            and policy.COORD_MIN <= p[1] <= policy.COORD_MAX)


def _constraints(order):
    c = order.get("constraints")
    return c if isinstance(c, dict) else {}


# --------------------------------------------------------------------------- #
# The evaluation
# --------------------------------------------------------------------------- #
def evaluate(state: Dict[str, Any], orders: List[Dict[str, Any]]) -> Report:
    """Evaluate a battlefield state + proposed orders. Returns a Report.

    `state`  : dict with `known_contacts` and (optionally) `friendly_units`,
               `threat_level`. Same object shape used offline and at the edge.
    `orders` : list of order dicts (v2 shape; v1 orders lacking engage_zones are
               tolerated — their engage checks simply find nothing).
    """
    rep = Report(policy.POLICY_VERSION)

    contacts = state.get("known_contacts", []) or []
    contact_by_id = {c.get("contact_id"): c for c in contacts if c.get("contact_id")}
    units = state.get("friendly_units", []) or []
    unit_by_id = {u.get("unit_id"): u for u in units if u.get("unit_id")}

    _check_state(rep, state, contacts)

    for order in orders:
        _check_order(rep, order, contacts, contact_by_id, unit_by_id)

    return rep


def _check_state(rep, state, contacts):
    # Threat-classification parity (WARN: at the edge threat_level may be stale).
    declared = state.get("threat_level")
    if declared is not None and contacts:
        want = policy.classify_threat(contacts)
        if declared != want:
            rep.add(
                "THREAT_MISCLASSIFIED", WARN, SCHEMA,
                f"threat_level={declared!r} but capability-weighted classifier "
                f"says {want!r} (score={round(policy.threat_score(contacts), 2)})",
                declared=declared, expected=want,
                score=round(policy.threat_score(contacts), 2),
            )

    # Per-contact schema hygiene — only when the field is present, so live/edge
    # contacts that aren't fully enriched don't spuriously fail.
    for c in contacts:
        t = c.get("type")
        cid = c.get("contact_id")
        if "engagement_radius" in c and t in policy.ENGAGEMENT_RADII:
            want = policy.ENGAGEMENT_RADII[t]
            if c["engagement_radius"] != want:
                rep.add(
                    "CONTACT_RADIUS_WRONG", WARN, SCHEMA,
                    f"contact {cid} ({t}) engagement_radius="
                    f"{c['engagement_radius']} != {want}",
                    contact_id=cid, got=c["engagement_radius"], expected=want,
                )
        if "vulnerable_unit_types" in c and t in policy.VULNERABLE_TO:
            want = policy.vulnerable_types_for(t)
            if c["vulnerable_unit_types"] != want:
                rep.add(
                    "VULN_TYPES_WRONG", WARN, SCHEMA,
                    f"contact {cid} ({t}) vulnerable_unit_types disagree with doctrine",
                    contact_id=cid, got=c.get("vulnerable_unit_types"), expected=want,
                )


def _check_order(rep, order, contacts, contact_by_id, unit_by_id):
    uid = order.get("unit_id")
    unit = unit_by_id.get(uid, {})
    utype = unit.get("type")
    upos = unit.get("pos")
    cons = _constraints(order)
    engage_zones = cons.get("engage_zones", []) or []
    avoid_zones = cons.get("avoid_zones", []) or []
    route = _route(order, upos)
    rtext = _reasoning_text(order)

    # -- coordinate bounds (target, anchors, zone centres) -------------------
    pts = []
    if order.get("target") is not None:
        pts.append(("target", order["target"]))
    for i, a in enumerate(order.get("anchors", [])):
        pts.append((f"anchor[{i}]", a))
    for i, z in enumerate(avoid_zones):
        if "pos" in z:
            pts.append((f"avoid_zone[{i}]", z["pos"]))
    for i, z in enumerate(engage_zones):
        if "pos" in z:
            pts.append((f"engage_zone[{i}]", z["pos"]))
    for label, p in pts:
        if not _in_bounds(p):
            rep.add(
                "COORD_OOR", ERROR, SCHEMA,
                f"{label} {list(p)} outside playable bounds "
                f"[{policy.COORD_MIN},{policy.COORD_MAX}]",
                unit_id=uid, where=label, point=list(p),
            )

    # -- engage zones: resolution, doctrine, reachability, geometry ----------
    engaged_contact_ids = set()
    for i, z in enumerate(engage_zones):
        tc = z.get("target_contact")
        contact = contact_by_id.get(tc)

        if contact is None:
            rep.add(
                "ENGAGE_TARGET_UNRESOLVED", ERROR, SCHEMA,
                f"engage_zone[{i}] target_contact={tc!r} does not resolve to a "
                f"known contact",
                unit_id=uid, target_contact=tc,
            )
            continue

        engaged_contact_ids.add(tc)
        ctype = contact.get("type")
        cpos = contact.get("pos")

        # Doctrine suitability — the outmatched unit must not be the engager.
        if utype and ctype and policy.is_mismatch(utype, ctype):
            rep.add(
                "ENGAGE_MISMATCH", ERROR, DOCTRINE,
                f"{uid} ({utype}) ordered to engage {tc} ({ctype}) — {utype} is "
                f"outmatched; re-task an overmatching platform and route around",
                unit_id=uid, unit_type=utype, contact_id=tc, contact_type=ctype,
            )

        # Support/soft-skin platforms shouldn't carry engage_zones at all.
        if utype in policy.NON_ENGAGING_TYPES:
            rep.add(
                "NON_ENGAGING_TYPE_ENGAGE", WARN, DOCTRINE,
                f"{uid} ({utype}) is a support/transport platform and should "
                f"carry avoid_zones, not an engage_zone",
                unit_id=uid, unit_type=utype, contact_id=tc,
            )

        # Reachability — the crux. Does the route ever bring this unit within
        # its OWN weapon reach of the target? (Standoff platforms satisfy this
        # from range; close-assault platforms must actually close.)
        if cpos is not None and utype in policy.FRIENDLY_REACH:
            reach = policy.FRIENDLY_REACH[utype]
            approach = geo.closest_approach_to_point(route, cpos)
            budget = reach + policy.REACH_SLACK
            if reach <= 0:
                rep.add(
                    "ENGAGE_UNREACHABLE", ERROR, GEOMETRY,
                    f"{uid} ({utype}) cannot engage {tc}: {utype} has no offensive "
                    f"reach (unarmed)",
                    unit_id=uid, unit_type=utype, contact_id=tc,
                )
            elif approach > budget:
                rep.add(
                    "ENGAGE_UNREACHABLE", ERROR, GEOMETRY,
                    f"{uid} ({utype}) declares engaging {tc} but its route's "
                    f"closest approach is {approach:.0f}m — beyond its {reach}m "
                    f"reach (+{policy.REACH_SLACK}m slack). The engagement can "
                    f"never be prosecuted.",
                    unit_id=uid, unit_type=utype, contact_id=tc,
                    closest_approach=round(approach, 1), reach=reach,
                )

        # Marker-box sanity: the engage_zone box should cover its target.
        if cpos is not None and "pos" in z and "radius" in z:
            d = geo.distance(z["pos"], cpos)
            if d > z["radius"]:
                rep.add(
                    "ENGAGE_ZONE_NOT_ON_CONTACT", WARN, GEOMETRY,
                    f"engage_zone[{i}] centre {list(z['pos'])} is {d:.0f}m from "
                    f"its target {tc} at {list(cpos)} — outside the zone's own "
                    f"{z['radius']}m radius",
                    unit_id=uid, contact_id=tc, offset=round(d, 1),
                    radius=z["radius"],
                )

    # -- avoid zones: no-entry, and no engaged target sitting inside one ------
    for i, z in enumerate(avoid_zones):
        zpos = z.get("pos")
        zr = z.get("radius")
        if zpos is None or zr is None:
            continue
        if geo.path_enters_circle(route, zpos, zr):
            rep.add(
                "AVOID_ENTERED", ERROR, GEOMETRY,
                f"{uid} route enters avoid_zone[{i}] at {list(zpos)} (r={zr}) — "
                f"avoid_zones are hard no-entry",
                unit_id=uid, zone_index=i, pos=list(zpos), radius=zr,
            )
        # Self-contradiction: a contact this order engages sits inside an
        # avoid_zone of the same order.
        for tc in engaged_contact_ids:
            c = contact_by_id.get(tc)
            if c and c.get("pos") is not None and geo.point_in_circle(c["pos"], zpos, zr):
                rep.add(
                    "ENGAGE_TARGET_IN_AVOID", ERROR, GEOMETRY,
                    f"{uid} engages {tc} but {tc} lies inside this order's "
                    f"avoid_zone[{i}] — contradictory tasking",
                    unit_id=uid, contact_id=tc, zone_index=i,
                )

    # -- reasoning-vs-geometry consistency (heuristic WARNs) -----------------
    claims_avoidance = any(p in rtext for p in _AVOIDANCE_PHRASES)
    tgt = order.get("target")
    for c in contacts:
        cid = c.get("contact_id")
        cpos = c.get("pos")
        crad = c.get("engagement_radius")
        if cpos is None or crad is None or cid in engaged_contact_ids:
            continue

        # Route runs through a threat's kill radius that reasoning never names.
        if geo.path_enters_circle(route, cpos, crad):
            ctype = c.get("type", "unknown")
            if ctype not in rtext and "threat" not in rtext and "contact" not in rtext:
                rep.add(
                    "UNACKNOWLEDGED_THREAT", WARN, REASONING,
                    f"{uid} route passes through {cid} ({ctype}) engagement "
                    f"radius but the reasoning never mentions it",
                    unit_id=uid, contact_id=cid, contact_type=ctype,
                )

        # Reasoning claims avoidance while the destination sits inside a threat.
        if claims_avoidance and tgt is not None and geo.distance(tgt, cpos) < crad:
            rep.add(
                "AVOIDANCE_CLAIM_CONTRADICTION", WARN, REASONING,
                f"{uid} reasoning claims avoidance/standoff but target "
                f"{list(tgt)} is {geo.distance(tgt, cpos):.0f}m inside {cid}'s "
                f"{crad}m radius",
                unit_id=uid, contact_id=cid,
                distance=round(geo.distance(tgt, cpos), 1), radius=crad,
            )


# --------------------------------------------------------------------------- #
# Normalizer — map either wire format into (state, orders)
# --------------------------------------------------------------------------- #
def _maybe_json(v):
    if isinstance(v, str):
        import json
        return json.loads(v)
    return v


def normalize_example(example: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Extract (state, orders) from either wire format.

    Accepts:
      * v2 dataset example: ``{state_json, teacher_output: {orders}}``
      * pipeline DB row:    ``{state_json, teacher_output_json: {orders}}``
        (state_json / teacher_output_json may be JSON strings — parsed here)
    Returns ``(state_dict, orders_list)``.
    """
    state = _maybe_json(example.get("state_json") or example.get("state") or {})

    teacher = example.get("teacher_output")
    if teacher is None:
        teacher = example.get("teacher_output_json")
    teacher = _maybe_json(teacher) or {}
    orders = teacher.get("orders", []) if isinstance(teacher, dict) else []

    return state, orders


def evaluate_example(example: Dict[str, Any]) -> Report:
    """Convenience: normalize an example and evaluate it in one call."""
    state, orders = normalize_example(example)
    return evaluate(state, orders)
