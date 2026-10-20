"""Cantilever snap-fit and flexure formulas (rectangular cross-section).

    strain      eps = 1.5 * t * y / L^2
    tip force   P   = w * t^2 * E * eps / (6 * L)
    assembly    W   = P * tan(alpha + rho),  rho = atan(mu)

t thickness, y deflection, L beam length, w width, alpha face angle.
"""

import math


def hook_length(t, y, strain):
    """Beam length that gives `strain` at deflection `y`."""
    return math.sqrt(1.5 * t * y / strain)


def strain(t, y, length):
    return 1.5 * t * y / length ** 2


def deflection_force(w, t, E, eps, length):
    return w * t ** 2 * E * eps / (6 * length)


def mating_force(P, angle_deg, mu):
    """Force along the closing direction to push a barb with face angle `angle_deg` past
    the edge (lead-in when closing, retention face when pulling apart)."""
    return P * math.tan(math.radians(angle_deg) + math.atan(mu))


def flexure_force(E, w, t, y, length):
    """Force at the tip of a flexure (cantilever) deflected by `y`."""
    return E * w * t ** 3 * y / (4 * length ** 3)
