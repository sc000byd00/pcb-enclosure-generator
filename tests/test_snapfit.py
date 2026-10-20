import math

from enclosure import snapfit


def test_hook_length_matches_hand_calculation():
    # t = 1.2 mm, deflection 0.75 mm, target strain 1.6 % -> L = 9.2 mm
    assert math.isclose(snapfit.hook_length(1.2, 0.75, 0.016), 9.186, abs_tol=1e-3)


def test_strain_is_inverse_of_hook_length():
    L = snapfit.hook_length(1.5, 0.6, 0.012)
    assert math.isclose(snapfit.strain(1.5, 0.6, L), 0.012)


def test_retention_face_holds_harder_than_lead_in():
    P = snapfit.deflection_force(6.0, 1.2, 2000.0, 0.016, 9.2)
    assert snapfit.mating_force(P, 45, 0.3) > snapfit.mating_force(P, 30, 0.3) > 0
