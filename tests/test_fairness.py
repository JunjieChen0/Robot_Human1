"""公平性指标的分母、缺类处理和只按验证成绩选型。"""

import numpy as np
import pandas as pd
import pytest

from src.fairness import audit, binary_labels, choose_candidate, wilson_interval


def test_binary_definition_does_not_merge_overweight_into_obesity():
    frame = pd.DataFrame({"NObeyesdad": ["Overweight_Level_II", "Obesity_Type_I", "Obesity_Type_III", "Normal_Weight"]})
    assert binary_labels(frame).tolist() == [0, 1, 1, 0]


def test_audit_uses_separate_positive_and_negative_denominators():
    y = np.array([1, 1, 0, 0, 1, 1, 0, 0])
    pred = np.array([1, 0, 0, 0, 1, 1, 1, 0])
    rows, overall = audit(y, pred, ["女性"] * 4 + ["男性"] * 4)
    female = rows.set_index("group").loc["女性"]
    assert female.tpr == .5 and female.fnr == .5 and female.fpr == 0
    assert female.balanced_accuracy == .75
    assert overall["equalized_odds_difference"] == .5
    assert overall["demographic_parity_difference"] == .5


def test_missing_class_is_not_reported_as_zero_error():
    rows, overall = audit([1, 1, 0, 1], [1, 1, 0, 0], ["女性", "女性", "男性", "男性"])
    female = rows.set_index("group").loc["女性"]
    assert np.isnan(female.fpr) and np.isnan(female.balanced_accuracy)
    assert np.isnan(overall["equalized_odds_difference"])
    assert "缺少" in female.reliability


def test_validation_selection_respects_both_performance_floors():
    frame = pd.DataFrame([
        dict(model="baseline", balanced_accuracy=.9, f1=.9, equalized_odds_difference=.15, bound=np.nan),
        dict(model="eo_0.01", balanced_accuracy=.87, f1=.9, equalized_odds_difference=0, bound=.01),
        dict(model="eo_0.02", balanced_accuracy=.9, f1=.87, equalized_odds_difference=0, bound=.02),
        dict(model="eo_0.05", balanced_accuracy=.89, f1=.89, equalized_odds_difference=.05, bound=.05),
    ])
    assert choose_candidate(frame) == "eo_0.05"


def test_zero_errors_still_have_nonzero_uncertainty():
    low, high = wilson_interval(0, 100)
    assert low == pytest.approx(0) and .03 < high < .04
    assert np.isnan(wilson_interval(0, 0)[0])
