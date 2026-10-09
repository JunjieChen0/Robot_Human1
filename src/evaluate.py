"""在独立测试集上评价最终模型并生成图表与演示档案。"""

from __future__ import annotations

import json

import joblib
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from src.config import (
    BINARY_FEATURES,
    FEATURE_NAMES,
    LABEL_COLUMN,
    LABEL_NAMES_ZH,
    LABEL_ORDER,
    MODELS_DIR,
    NOMINAL_BASELINE,
    NOMINAL_DUMMIES,
    NOMINAL_FEATURE,
    NUMERIC_FEATURES,
    ORDINAL_FEATURES,
    ORDINAL_LEVELS,
    PROCESSED_DIR,
    REPORT_FIGURES_DIR,
    REPORT_TABLES_DIR,
    SAMPLE_DIR,
)


matplotlib.use("Agg")

RAW_FIELDS = (
    list(NUMERIC_FEATURES)
    + list(BINARY_FEATURES)
    + list(ORDINAL_FEATURES)
    + [NOMINAL_FEATURE]
)


def _save_confusion_matrix(matrix: np.ndarray, normalized: bool = False) -> None:
    REPORT_FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    labels = list(LABEL_ORDER)
    plt.figure(figsize=(9, 7))
    image = plt.imshow(matrix, interpolation="nearest", cmap="Blues")
    plt.colorbar(image, fraction=0.046, pad=0.04)
    threshold = float(np.nanmax(matrix)) / 2.0 if matrix.size else 0.0
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix[row, column]
            text = f"{value:.2f}" if normalized else f"{int(value)}"
            color = "white" if value > threshold else "black"
            plt.text(column, row, text, ha="center", va="center", color=color)
    plt.xticks(range(len(labels)), labels, rotation=30, ha="right")
    plt.yticks(range(len(labels)), labels)
    plt.xlabel("Predicted label")
    plt.ylabel("True label")
    plt.title("Normalized confusion matrix" if normalized else "Confusion matrix")
    plt.tight_layout()
    filename = "normalized_confusion_matrix.png" if normalized else "confusion_matrix.png"
    plt.savefig(REPORT_FIGURES_DIR / filename, dpi=160)
    plt.close()


def _save_class_distribution(frame: pd.DataFrame) -> None:
    counts = (
        frame[LABEL_COLUMN]
        .value_counts()
        .reindex(LABEL_ORDER)
        .fillna(0)
    )
    plt.figure(figsize=(9, 5))
    plt.bar(list(counts.index), counts.values, color="#59a14f")
    plt.ylabel("Samples")
    plt.xlabel("Obesity level")
    plt.title("Class distribution (test)")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(REPORT_FIGURES_DIR / "class_distribution.png", dpi=160)
    plt.close()


def _decode_profile(row: pd.Series) -> dict[str, object]:
    """把编码后的特征行还原为原型表单可用的原始字段值。"""

    profile: dict[str, object] = {}
    for column in NUMERIC_FEATURES:
        profile[column] = round(float(row[column]), 3)
    for column in BINARY_FEATURES:
        if column == "Gender":
            profile[column] = "Male" if int(row[column]) == 1 else "Female"
        else:
            profile[column] = "yes" if int(row[column]) == 1 else "no"
    inverse = {value: key for key, value in ORDINAL_LEVELS.items()}
    for column in ORDINAL_FEATURES:
        profile[column] = inverse[int(row[column])]
    dummy_hits = [level for level in NOMINAL_DUMMIES if int(row[f"{NOMINAL_FEATURE}_{level}"]) == 1]
    profile[NOMINAL_FEATURE] = dummy_hits[0] if dummy_hits else NOMINAL_BASELINE
    return profile


def _save_demo_profiles(frame: pd.DataFrame, predictions: np.ndarray) -> None:
    """每个类别取指定数据集中第一个被判对的样本作为原型演示档案。

    演示档案仅用于原型演示表单操作流程；为避免把留出测试集当作演示池，
    调用方应传入训练集。
    """

    correct = frame.loc[frame[LABEL_COLUMN].to_numpy() == predictions]
    rows = []
    for label in LABEL_ORDER:
        candidates = correct[correct[LABEL_COLUMN].eq(label)]
        if candidates.empty:
            raise ValueError(f"数据集中没有类别 {label} 被判对的样本，无法生成演示档案。")
        profile = _decode_profile(candidates.iloc[0])
        rows.append({"sample_id": f"demo_{label.lower()}", "label": label, **profile})
    pd.DataFrame(rows).to_csv(SAMPLE_DIR / "demo_profiles.csv", index=False)


def evaluate_final_model() -> dict[str, object]:
    for directory in (REPORT_TABLES_DIR, REPORT_FIGURES_DIR, SAMPLE_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    data_path = PROCESSED_DIR / "features.csv"
    model_path = MODELS_DIR / "final_model.joblib"
    if not data_path.is_file() or not model_path.is_file():
        raise FileNotFoundError("请先运行预处理和训练步骤。")

    frame = pd.read_csv(data_path)
    test_frame = frame[frame["split"].eq("test")].copy()
    train_frame = frame[frame["split"].eq("train")].copy()
    model = joblib.load(model_path)
    y_true = test_frame[LABEL_COLUMN].to_numpy()
    predictions = model.predict(test_frame[FEATURE_NAMES])
    probabilities = model.predict_proba(test_frame[FEATURE_NAMES])

    report = classification_report(
        y_true,
        predictions,
        labels=LABEL_ORDER,
        target_names=[LABEL_NAMES_ZH[name] for name in LABEL_ORDER],
        output_dict=True,
        zero_division=0,
    )
    report_frame = pd.DataFrame(report).T.reset_index(names="class")
    report_frame.to_csv(REPORT_TABLES_DIR / "test_classification_report.csv", index=False)

    matrix = confusion_matrix(y_true, predictions, labels=LABEL_ORDER)
    normalized_matrix = matrix.astype(float) / matrix.sum(axis=1, keepdims=True)
    _save_confusion_matrix(matrix, normalized=False)
    _save_confusion_matrix(normalized_matrix, normalized=True)
    _save_class_distribution(test_frame)
    # 演示档案只取自训练集：测试集仅用于最终评价，不作为演示池
    train_predictions = model.predict(train_frame[FEATURE_NAMES])
    _save_demo_profiles(train_frame, train_predictions)

    # predict_proba 的列按分类器 classes_ 顺序排列（字母序），必须用 classes_ 命名，
    # 不能用 LABEL_ORDER（语义序），否则概率列名与数值错位。
    probability_frame = pd.DataFrame(
        probabilities,
        columns=[f"prob_{name}" for name in model.named_steps["classifier"].classes_],
    )
    prediction_frame = pd.concat(
        [
            test_frame[[LABEL_COLUMN]].reset_index(drop=True),
            pd.DataFrame({"predicted": predictions}),
            pd.DataFrame({"top_probability": probabilities.max(axis=1)}),
            probability_frame.reset_index(drop=True),
        ],
        axis=1,
    )
    prediction_frame.to_csv(REPORT_TABLES_DIR / "test_predictions.csv", index=False)

    error_mask = y_true != predictions
    error_frame = prediction_frame.loc[error_mask].copy()
    error_frame.to_csv(REPORT_TABLES_DIR / "error_cases.csv", index=False)

    summary = {
        "accuracy": float(accuracy_score(y_true, predictions)),
        "test_samples": int(len(test_frame)),
        "error_samples": int(error_mask.sum()),
        "error_rate": float(error_mask.mean()),
        "confusion_matrix": matrix.tolist(),
    }
    (REPORT_TABLES_DIR / "test_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(report_frame.to_string(index=False))
    return summary


def main() -> None:
    evaluate_final_model()


if __name__ == "__main__":
    main()
