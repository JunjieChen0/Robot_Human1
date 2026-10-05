"""UCI 544 数据读取、质量检查、编码和分层划分。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.config import (
    BINARY_FEATURES,
    FEATURE_NAMES,
    LABEL_COLUMN,
    LABEL_ORDER,
    NOMINAL_BASELINE,
    NOMINAL_DUMMIES,
    NOMINAL_FEATURE,
    NUMERIC_FEATURES,
    ORDINAL_FEATURES,
    ORDINAL_LEVELS,
    PROCESSED_DIR,
    RANDOM_STATE,
    RAW_CSV,
    REPORT_TABLES_DIR,
    SAMPLE_DIR,
)


def encode_features(frame: pd.DataFrame) -> pd.DataFrame:
    """把原始问卷字段编码为数值特征矩阵。"""

    encoded = pd.DataFrame(index=frame.index)
    for column in NUMERIC_FEATURES:
        encoded[column] = frame[column].astype(float)
    for column in BINARY_FEATURES:
        if column == "Gender":
            encoded[column] = frame[column].map({"Male": 1, "Female": 0}).astype(float)
        else:
            encoded[column] = frame[column].map({"yes": 1, "no": 0}).astype(float)
    for column in ORDINAL_FEATURES:
        encoded[column] = frame[column].map(ORDINAL_LEVELS).astype(float)
    for level in NOMINAL_DUMMIES:
        encoded[f"{NOMINAL_FEATURE}_{level}"] = (
            frame[NOMINAL_FEATURE].eq(level).astype(float)
        )
    if encoded.isna().any().any():
        bad = encoded.columns[encoded.isna().any()].tolist()
        raise ValueError(f"编码后存在无法识别的取值，涉及列：{bad}")
    return encoded[FEATURE_NAMES]


def assign_splits(
    frame: pd.DataFrame,
    random_state: int = RANDOM_STATE,
) -> pd.DataFrame:
    """按标签分层划分 train/validation/test = 60/20/20。

    数据集为横断面调查与合成样本的混合，没有受试者编号，因此不做分组划分；
    划分口径会在报告中说明。
    """

    result = frame.copy()
    train_frame, rest_frame = train_test_split(
        result,
        test_size=0.4,
        stratify=result[LABEL_COLUMN],
        random_state=random_state,
    )
    validation_frame, test_frame = train_test_split(
        rest_frame,
        test_size=0.5,
        stratify=rest_frame[LABEL_COLUMN],
        random_state=random_state,
    )
    result["split"] = "train"
    result.loc[validation_frame.index, "split"] = "validation"
    result.loc[test_frame.index, "split"] = "test"
    return result


def _quality_report(frame: pd.DataFrame) -> dict[str, object]:
    feature_values = frame[FEATURE_NAMES]
    return {
        "rows": int(len(frame)),
        "feature_count": len(FEATURE_NAMES),
        "missing_total": int(frame.isna().sum().sum()),
        "non_finite_total": int(
            (~np.isfinite(feature_values.to_numpy(dtype=float))).sum()
        ),
        "duplicate_full_rows": int(frame.duplicated().sum()),
        "class_counts": frame[LABEL_COLUMN].value_counts().reindex(LABEL_ORDER).to_dict(),
        "split_counts": frame["split"].value_counts().to_dict(),
        "split_rule": "按标签分层随机划分 60/20/20；数据集无受试者编号，不做分组划分",
    }


def build_processed_dataset() -> pd.DataFrame:
    for directory in (PROCESSED_DIR, SAMPLE_DIR, REPORT_TABLES_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(RAW_CSV)
    if not set(raw[LABEL_COLUMN].unique()).issubset(set(LABEL_ORDER)):
        raise ValueError("数据中存在未知肥胖等级标签。")

    frame = encode_features(raw)
    frame.insert(0, LABEL_COLUMN, raw[LABEL_COLUMN].to_numpy())
    frame = assign_splits(frame)

    frame.to_csv(PROCESSED_DIR / "features.csv", index=False)
    quality = _quality_report(frame)
    (PROCESSED_DIR / "data_quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 注意：训练/验证集的取值范围由 src.train 写入 models/raw_ranges.json，
    # 这里不再重复产出 data/processed/raw_ranges.json，避免双份维护。

    template = {column: float(frame.loc[frame["split"].eq("train"), column].median())
                for column in NUMERIC_FEATURES}
    template.update({column: 0.0 for column in BINARY_FEATURES})
    template.update({column: 1.0 for column in ORDINAL_FEATURES})
    template.update({f"{NOMINAL_FEATURE}_{level}": 0.0 for level in NOMINAL_DUMMIES})
    pd.DataFrame([template]).to_csv(SAMPLE_DIR / "input_template.csv", index=False)

    print(f"处理完成：{PROCESSED_DIR / 'features.csv'}")
    print(json.dumps(quality, ensure_ascii=False, indent=2))
    return frame


def main() -> None:
    build_processed_dataset()


if __name__ == "__main__":
    main()
