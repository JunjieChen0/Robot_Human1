"""训练并比较逻辑回归和随机森林模型。"""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import (
    FEATURE_NAMES,
    LABEL_COLUMN,
    LABEL_NAMES_ZH,
    LABEL_ORDER,
    MODELS_DIR,
    NUMERIC_FEATURES,
    PROCESSED_DIR,
    RANDOM_STATE,
    REPORT_TABLES_DIR,
)


def build_models(random_state: int = RANDOM_STATE) -> dict[str, Pipeline]:
    return {
        "LogisticRegression": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                ("classifier", LogisticRegression(max_iter=3000, random_state=random_state)),
            ]
        ),
        "RandomForest": Pipeline(
            steps=[
                (
                    "classifier",
                    RandomForestClassifier(n_estimators=300, random_state=random_state, n_jobs=-1),
                )
            ]
        ),
    }


def _metric_row(model_name: str, y_true: pd.Series, y_pred: np.ndarray) -> dict[str, object]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=LABEL_ORDER, average="macro", zero_division=0
    )
    return {
        "model": model_name,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision),
        "recall_macro": float(recall),
        "f1_macro": float(f1),
    }


def _raw_ranges(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {
        column: {
            "min": float(frame[column].min()),
            "max": float(frame[column].max()),
            "median": float(frame[column].median()),
        }
        for column in NUMERIC_FEATURES
    }


def _feature_importance(model: Pipeline) -> list[dict[str, object]]:
    classifier = model.named_steps["classifier"]
    if hasattr(classifier, "feature_importances_"):
        values = np.asarray(classifier.feature_importances_, dtype=float)
    elif hasattr(classifier, "coef_"):
        values = np.mean(np.abs(np.asarray(classifier.coef_, dtype=float)), axis=0)
    else:
        values = np.zeros(len(FEATURE_NAMES), dtype=float)
    total = float(values.sum())
    if total > 0:
        values = values / total
    return sorted(
        (
            {"feature": feature, "importance": float(value)}
            for feature, value in zip(FEATURE_NAMES, values)
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )


def train_and_compare() -> dict[str, object]:
    for directory in (MODELS_DIR, REPORT_TABLES_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    data_path = PROCESSED_DIR / "features.csv"
    if not data_path.is_file():
        raise FileNotFoundError("没有找到处理后的数据，请先运行 python -m src.preprocess。")

    frame = pd.read_csv(data_path)
    train_frame = frame[frame["split"].eq("train")]
    validation_frame = frame[frame["split"].eq("validation")]
    fit_frame = frame[frame["split"].isin(["train", "validation"])]

    validation_rows = []
    validation_reports: dict[str, dict[str, dict[str, float]]] = {}
    for model_name, model in build_models().items():
        model.fit(train_frame[FEATURE_NAMES], train_frame[LABEL_COLUMN])
        predictions = model.predict(validation_frame[FEATURE_NAMES])
        validation_rows.append(
            _metric_row(model_name, validation_frame[LABEL_COLUMN], predictions)
        )
        validation_reports[model_name] = classification_report(
            validation_frame[LABEL_COLUMN],
            predictions,
            labels=LABEL_ORDER,
            output_dict=True,
            zero_division=0,
        )

    comparison = pd.DataFrame(validation_rows).sort_values(
        by=["f1_macro", "accuracy"], ascending=False
    )
    comparison.to_csv(REPORT_TABLES_DIR / "model_comparison.csv", index=False)
    (REPORT_TABLES_DIR / "validation_classification_reports.json").write_text(
        json.dumps(validation_reports, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    selected_model_name = str(comparison.iloc[0]["model"])
    final_model = build_models()[selected_model_name]
    final_model.fit(fit_frame[FEATURE_NAMES], fit_frame[LABEL_COLUMN])
    joblib.dump(final_model, MODELS_DIR / "final_model.joblib")

    metadata = {
        "model_name": selected_model_name,
        "feature_names": FEATURE_NAMES,
        "label_mapping": {
            name: {"name_zh": LABEL_NAMES_ZH[name]} for name in LABEL_ORDER
        },
        "random_state": RANDOM_STATE,
        "validation_selection_metric": "f1_macro",
        "training_samples": int(len(train_frame)),
        "validation_samples": int(len(validation_frame)),
        "final_fit_samples": int(len(fit_frame)),
        "global_feature_importance": _feature_importance(final_model),
        "probability_note": "predict_proba 输出为模型类别概率估计，未自动解释为校准后的真实置信度。",
    }
    (MODELS_DIR / "model_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (MODELS_DIR / "raw_ranges.json").write_text(
        json.dumps(_raw_ranges(train_frame), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("验证集模型比较：")
    print(comparison.to_string(index=False))
    print(f"最终模型：{selected_model_name}")
    return metadata


def main() -> None:
    train_and_compare()


if __name__ == "__main__":
    main()
