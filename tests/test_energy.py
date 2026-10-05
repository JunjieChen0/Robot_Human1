from src.energy import activity_level_from_exercise, bmr_mifflin_st_jeor, project_weight, tdee


def test_bmr_matches_mifflin_st_jeor_reference_values():
    assert bmr_mifflin_st_jeor(80.0, 1.80, 30.0, True) == 1780.0
    assert bmr_mifflin_st_jeor(80.0, 1.80, 30.0, False) == 1614.0


def test_activity_level_thresholds():
    assert activity_level_from_exercise(0.0) == "久坐"
    assert activity_level_from_exercise(2.0) == "轻度活动"
    assert activity_level_from_exercise(4.0) == "中度活动"
    assert activity_level_from_exercise(6.0) == "高度活动"


def test_tdee_scales_with_activity_factor():
    sedentary = tdee(70.0, 1.70, 25.0, True, "久坐")
    active = tdee(70.0, 1.70, 25.0, True, "高度活动")
    assert active > sedentary


def test_energy_deficit_reduces_projected_weight():
    points = project_weight(70.0, 1800.0, 2570.0, 10, step_days=10)
    assert points[0]["weight_kg"] == 70.0
    assert points[-1]["day"] == 10.0
    assert abs(points[-1]["weight_kg"] - 69.0) < 1e-9


def test_energy_surplus_increases_projected_weight():
    points = project_weight(70.0, 3340.0, 2570.0, 10, step_days=10)
    assert points[-1]["weight_kg"] > 70.0
