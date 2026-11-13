import hashlib
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import balanced_accuracy_score

from src.config import FEATURE_NAMES, LABEL_COLUMN, MODELS_DIR, PROCESSED_DIR
from src.model_judgment import OUTPUT, distribution_table, permutation_scores, summarize_importance
from src.model_judgment_ui import importance_chart


class OppositeRule:
    def predict(self, frame):
        return frame.Weight.to_numpy().astype(int)


def test_permutation_keeps_zero_and_negative_drops_and_does_not_mutate_inputs():
    features = pd.DataFrame({"Weight": [0, 1] * 10, "CH2O": [2.] * 20})
    original = features.copy()
    labels = 1 - features.Weight
    baseline, repeated = permutation_scores(OppositeRule(), features, labels, ["Weight", "CH2O"], repeats=12)
    assert baseline == 0
    assert (repeated.loc[repeated.feature.eq("CH2O"), "score_drop"] == 0).all()
    assert repeated.loc[repeated.feature.eq("Weight"), "score_drop"].mean() < 0
    pd.testing.assert_frame_equal(features, original)
    assert np.allclose(repeated.score_drop, repeated.baseline_score - repeated.shuffled_score)
    _, rerun = permutation_scores(OppositeRule(), features, labels, ["Weight", "CH2O"], repeats=12)
    pd.testing.assert_frame_equal(repeated, rerun)
    importance = summarize_importance(repeated)
    assert set(importance.feature) == {"Weight", "CH2O"}
    spec = importance_chart(importance, "CH2O").to_dict()
    assert spec["layer"][0]["encoding"]["x"]["scale"]["domain"][0] < importance.low.min() * 100
    assert spec["params"][0]["select"]["fields"] == ["feature"]


def test_frozen_experiment_uses_training_only_and_prototype_validation_inputs():
    summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
    data = pd.read_csv(PROCESSED_DIR / "features.csv")
    records = pd.read_csv(OUTPUT / "validation_records.csv")
    train = data.loc[data.split.eq("train")]
    validation = data.loc[data.split.eq("validation")]
    assert summary["fit_split"] == "train" and summary["test_samples_used"] == 0
    assert records.source_csv_row.tolist() == (validation.index + 2).tolist()
    assert summary["train_samples"] == len(train)
    for feature, median in summary["imputed_values"].items():
        assert median == train[feature].median()
        assert records[feature].eq(median).all()
    model_path = MODELS_DIR / "judgment_model.joblib"
    # 模型文件不随Git分发；仅有冻结产物时仍可验证分数、划分及案例。
    if model_path.exists():
        model = joblib.load(model_path)
        assert all(tree.tree_.weighted_n_node_samples[0] == len(train) for tree in model.named_steps["classifier"].estimators_)
        np.testing.assert_array_equal(model.predict(records[FEATURE_NAMES]), records.predicted_label)
        assert hashlib.sha256(model_path.read_bytes()).hexdigest() == summary["model_sha256"]
    assert summary["baseline_score"] == pytest.approx(balanced_accuracy_score(records.true_label, records.predicted_label))
    assert records.true_label.tolist() == validation[LABEL_COLUMN].tolist()
    assert int(records.correct.sum()) == summary["correct_count"]
    assert int((~records.correct).sum()) == summary["error_count"]
    repeated = pd.read_csv(OUTPUT / "permutation_repeats.csv")
    pd.testing.assert_frame_equal(summarize_importance(repeated), pd.read_csv(OUTPUT / "feature_importance.csv"), check_exact=False)


@pytest.mark.parametrize("feature", ["Age", "FAF", "CH2O", "Weight", "Height"])
def test_distribution_uses_all_validation_records(feature):
    records = pd.read_csv(OUTPUT / "validation_records.csv")
    table = distribution_table(records, feature)
    assert table["样本量"].sum() == len(records)
    assert table["占比"].sum() == pytest.approx(1)
    if feature == "CH2O":
        assert (table["样本量"] == 0).any()


def test_age_distribution_handles_fractional_ages_and_boundaries():
    records = pd.DataFrame({"Age": [17.9, 18, 24.9, 25, 65]})
    assert distribution_table(records, "Age")["样本量"].tolist() == [1, 2, 1, 0, 0, 1]
