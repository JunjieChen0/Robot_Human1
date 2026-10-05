import pandas as pd

from src.validation import validate_profile, validate_weight_log, warn_outside_training_range


def valid_row() -> dict:
    return {
        "Age": 25.0,
        "Height": 1.70,
        "Weight": 70.0,
        "FCVC": 2.0,
        "NCP": 3.0,
        "CH2O": 2.0,
        "FAF": 2.0,
        "TUE": 1.0,
        "Gender": "Female",
        "family_history_with_overweight": "no",
        "FAVC": "no",
        "SMOKE": "no",
        "SCC": "yes",
        "CAEC": "Sometimes",
        "CALC": "Sometimes",
        "MTRANS": "Walking",
    }


def test_validate_profile_accepts_valid_input():
    clean, errors = validate_profile(valid_row())
    assert not errors
    assert clean["Weight"] == 70.0


def test_validate_profile_rejects_out_of_range_and_bad_category():
    row = valid_row()
    row["Age"] = 300.0
    row["CAEC"] = "often"
    clean, errors = validate_profile(row)
    assert any("年龄" in error or "Age" in error for error in errors)
    assert any("CAEC" in error for error in errors)


def test_warn_outside_training_range():
    clean, _ = validate_profile(valid_row())
    warnings = warn_outside_training_range(clean, {"Weight": {"min": 50.0, "max": 60.0}})
    assert any("Weight" in warning or "体重" in warning for warning in warnings)


def test_validate_weight_log_requires_two_rows():
    log, errors, _ = validate_weight_log(
        pd.DataFrame([{"date": "2026-09-01", "weight_kg": 70.0}])
    )
    assert errors
    assert log.empty or len(log) == 1


def test_validate_weight_log_rejects_bad_dates_and_negative_weight():
    frame = pd.DataFrame(
        [
            {"date": "not-a-date", "weight_kg": 70.0},
            {"date": "2026-09-02", "weight_kg": -5.0},
        ]
    )
    _, errors, _ = validate_weight_log(frame)
    assert any("日期" in error for error in errors)
    assert any("正数" in error for error in errors)


def test_validate_weight_log_sorts_by_date():
    frame = pd.DataFrame(
        [
            {"date": "2026-09-10", "weight_kg": 70.0},
            {"date": "2026-09-01", "weight_kg": 71.0},
        ]
    )
    log, errors, _ = validate_weight_log(frame)
    assert not errors
    assert log["weight_kg"].tolist() == [71.0, 70.0]
