"""Pure 2-D geometry for the Guardrail Kernel.

No dependencies, no I/O. Every function is a total function of its inputs so the
same call gives the same verdict offline and at the edge. Points are ``[x, y]``
(a third ``z`` component, if present, is ignored — the ladder and zone checks
are planar; line-of-sight/masking would be a separate 3-D concern).
"""

import math


def distance(a, b):
    """Euclidean distance between two points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_in_circle(p, center, radius):
    """True if p lies within (<=) the circle."""
    return distance(p, center) <= radius


def _closest_point_on_segment(p, a, b):
    """Closest point to p on segment a->b, and the parametric t in [0,1]."""
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0.0:            # degenerate segment
        return (ax, ay), 0.0
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / denom
    t = max(0.0, min(1.0, t))
    return (ax + t * dx, ay + t * dy), t


def dist_point_to_segment(p, a, b):
    """Shortest distance from point p to segment a->b."""
    q, _ = _closest_point_on_segment(p, a, b)
    return distance(p, q)


def segment_intersects_circle(a, b, center, radius):
    """True if segment a->b comes within `radius` of `center` (touches/enters)."""
    return dist_point_to_segment(center, a, b) <= radius


def closest_approach_to_point(path, target):
    """Minimum distance from a polyline `path` (list of points) to `target`.

    Considers both the vertices and the interiors of every segment, so a route
    that skims past a target between two anchors is measured correctly rather
    than only at the anchors. Returns ``inf`` for an empty path.
    """
    if not path:
        return float("inf")
    if len(path) == 1:
        return distance(path[0], target)
    best = float("inf")
    for i in range(len(path) - 1):
        d = dist_point_to_segment(target, path[i], path[i + 1])
        if d < best:
            best = d
    return best


def path_enters_circle(path, center, radius):
    """True if any segment (or vertex) of the polyline enters the circle.

    A single-point path is treated as that point; an empty path enters nothing.
    """
    if not path:
        return False
    if len(path) == 1:
        return point_in_circle(path[0], center, radius)
    for i in range(len(path) - 1):
        if segment_intersects_circle(path[i], path[i + 1], center, radius):
            return True
    return False
