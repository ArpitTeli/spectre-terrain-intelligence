"""SPECTRE Guardrail Policy — the single versioned source of truth for every
number the kernel enforces.

This module is deliberately **self-contained and dependency-free** so the whole
`guardrails/` package can be copy-pasted verbatim into:
  * the offline data-generation pipeline (spectre-terrain-intelligence), and
  * the deployed edge Tasking Layer (spectre-app),
and both run the *identical* checks against the *identical* constants. That
byte-for-byte sameness is the train/serve parity guarantee — a guardrail that
rejects a training example must reject the same order at the edge, or the model
learns a policy its runtime will veto.

Because the constants are vendored here rather than imported from the repo-root
``doctrine.py`` / ``threat.py``, drift is possible. It is caught, not prevented:
``conformance.py::test_policy_matches_legacy`` asserts these tables equal the
legacy modules exactly, so any divergence fails the suite loudly.

POLICY_VERSION is stamped into every Report. Training data and the edge model
must be built against the same version; bump it whenever any constant below
changes and re-run conformance before shipping either side.
"""

POLICY_VERSION = "2.0.0"


# --------------------------------------------------------------------------- #
# 1. Coordinate / schema bounds (Stratis playable area, v2 dataset envelope)
# --------------------------------------------------------------------------- #
COORD_MIN = 1000
COORD_MAX = 7000

CONFIDENCE_MIN = 0.6
CONFIDENCE_MAX = 1.0

ZONE_RADIUS_MIN = 150
ZONE_RADIUS_MAX = 300

ANCHORS_MIN = 2
ANCHORS_MAX = 5

REASONING_MIN_CHARS = 40
REASONING_KEYS = (
    "situation_assessment",
    "tactical_choice",
    "tradeoffs",
    "what_if_rejected",
)

OBJECTIVES = frozenset(
    {"attack", "defend", "patrol", "evacuate", "recon", "hold", "support"}
)
INTENTS = frozenset(
    {"attack", "defend", "move", "hold", "recon", "evacuate", "support"}
)
PREFER_SURFACES = frozenset({"road", "forest", None})


# --------------------------------------------------------------------------- #
# 2. Enemy engagement radii (metres) — how far a *threat* of each type reaches.
#    A contact's engagement_radius MUST equal its type's value exactly.
# --------------------------------------------------------------------------- #
ENGAGEMENT_RADII = {
    "mbt": 1200,
    "ifv": 800,
    "apc": 600,
    "mrap": 500,
    "light": 400,
    "truck": 300,
    "infantry": 300,
    "helicopter": 1500,
}


# --------------------------------------------------------------------------- #
# 3. Friendly weapon reach (metres) — how close a *friendly* unit of each type
#    must get to a target contact before it can bring effective fire.
#
#    This is the crux of the engage-satisfaction predicate. It is DISTINCT from
#    the enemy ENGAGEMENT_RADII above and from the engage_zone.radius marker
#    (150-300). A standoff platform (mbt/ifv/helicopter) satisfies an engagement
#    by reaching *its own* long reach — it need never enter a small box centred
#    on the target. A close-assault platform (infantry/light/mrap) has short
#    reach, so the same predicate demands it actually close.
#
#    truck = 0: an unarmed transport can never satisfy an engagement (and should
#    never carry an engage_zone). spg/spaa/eng: indirect / air-defence / support
#    — direct-fire engage_zones are out of doctrine for them (see doctrine.py
#    soft-skin convention), so their reach here is advisory only.
# --------------------------------------------------------------------------- #
FRIENDLY_REACH = {
    "mbt": 1200,
    "ifv": 800,
    "apc": 600,
    "mrap": 500,
    "light": 400,
    "infantry": 300,
    "helicopter": 1500,
    "truck": 0,
    "spg": 700,   # indirect — advisory; direct-fire engage_zones out of doctrine
    "spaa": 500,  # air-defence — advisory
    "eng": 300,   # engineer dismounts — advisory
}

# Slack (metres) added to FRIENDLY_REACH when deciding whether an engagement is
# physically satisfiable. Absorbs the ~50m path-planner waypoint spacing and
# anchor granularity so we don't flag a unit that stops one grid-cell short of
# nominal reach. Kept small — it forgives snapping, not a real standoff gap.
REACH_SLACK = 60


# --------------------------------------------------------------------------- #
# 4. Threat weighting & classification (capability-weighted, half-open buckets).
#    Mirror of threat.py — see threat_level.md for the rationale.
# --------------------------------------------------------------------------- #
THREAT_POINTS = {
    "mbt": 5,
    "ifv": 4,
    "apc": 3.75,
    "mrap": 3.2,
    "light": 2.5,
    "truck": 0.5,
    "infantry": 1,
    "helicopter": 5,
}
FORCES_HIGH = ("mbt", "ifv", "helicopter")
THREAT_HIGH_MIN = 9   # total >= 9        -> high
THREAT_MED_MIN = 4    # 4 <= total < 9    -> medium ; < 4 -> low


def threat_score(contacts):
    """Sum of threat points across contact dicts (each with a 'type')."""
    return sum(THREAT_POINTS.get(c["type"], 1) for c in contacts)


def classify_threat(contacts):
    """'low' | 'medium' | 'high' — capability-weighted. Mirror of threat.classify."""
    if any(c["type"] in FORCES_HIGH for c in contacts):
        return "high"
    total = threat_score(contacts)
    if total >= THREAT_HIGH_MIN:
        return "high"
    if total >= THREAT_MED_MIN:
        return "medium"
    return "low"


# --------------------------------------------------------------------------- #
# 5. Doctrine matrix — enemy contact type -> friendly types it OUTMATCHES.
#    Mirror of doctrine.py. The engage-suitability gate: ordering a listed unit
#    to engage that contact is a doctrine mismatch.
# --------------------------------------------------------------------------- #
VULNERABLE_TO = {
    "mbt": ["apc", "mrap", "light", "truck", "spg", "spaa", "eng", "infantry"],
    "ifv": ["apc", "mrap", "light", "truck", "spg", "spaa", "eng", "infantry"],
    "apc": ["mrap", "light", "truck", "spg", "spaa", "eng", "infantry"],
    "mrap": ["light", "truck", "spg", "spaa", "eng", "infantry"],
    "light": ["truck", "spg", "spaa", "eng", "infantry"],
    "truck": [],
    "infantry": ["mrap", "light", "truck", "spg", "spaa", "eng"],
}

# Direct-fire support platforms that carry avoid_zones only, never engage_zones,
# by convention (spg/spaa fight from defilade/rear; truck is unarmed; eng is not
# a direct-fire fighter). Used to WARN if one is handed an engage_zone.
NON_ENGAGING_TYPES = frozenset({"truck", "spg", "spaa", "eng"})


def vulnerable_types_for(contact_type):
    """The vulnerable_unit_types list to stamp on a contact of this type."""
    return list(VULNERABLE_TO.get(contact_type, []))


def is_mismatch(unit_type, contact_type):
    """True if ordering `unit_type` to engage `contact_type` is a doctrine mismatch."""
    return unit_type in VULNERABLE_TO.get(contact_type, [])


# --------------------------------------------------------------------------- #
# 6. Export for the edge (JS/other runtimes) — the identical numbers as JSON so
#    a non-Python edge reimplementation loads the same policy this kernel uses.
# --------------------------------------------------------------------------- #
def as_dict():
    """The full policy as plain data, for JSON export / cross-runtime parity."""
    return {
        "policy_version": POLICY_VERSION,
        "coord_min": COORD_MIN,
        "coord_max": COORD_MAX,
        "confidence_min": CONFIDENCE_MIN,
        "confidence_max": CONFIDENCE_MAX,
        "zone_radius_min": ZONE_RADIUS_MIN,
        "zone_radius_max": ZONE_RADIUS_MAX,
        "anchors_min": ANCHORS_MIN,
        "anchors_max": ANCHORS_MAX,
        "reasoning_min_chars": REASONING_MIN_CHARS,
        "reasoning_keys": list(REASONING_KEYS),
        "objectives": sorted(OBJECTIVES),
        "intents": sorted(INTENTS),
        "prefer_surfaces": ["road", "forest", None],
        "engagement_radii": ENGAGEMENT_RADII,
        "friendly_reach": FRIENDLY_REACH,
        "reach_slack": REACH_SLACK,
        "threat_points": THREAT_POINTS,
        "forces_high": list(FORCES_HIGH),
        "threat_high_min": THREAT_HIGH_MIN,
        "threat_med_min": THREAT_MED_MIN,
        "vulnerable_to": VULNERABLE_TO,
        "non_engaging_types": sorted(NON_ENGAGING_TYPES),
    }
