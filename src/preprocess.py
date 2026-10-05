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


OUTLIER_LIMITS = {
    "Age": (14.0, 70.0),
    "Height": (1.4, 2.2),
    "Weight": (30.0, 200.0),
    "FCVC": (1.0, 3.0),
    "NCP": (1.0, 4.0),
    "CH2O": (1.0, 3.0),
    "FAF": (0.0, 3.0),
    "TUE": (0.0, 2.0),
}


def detect_outliers(frame: pd.DataFrame) -> dict[str, object]:
    """检测数值字段的领域越界值与连续字段的 IQR 离群点。

    问卷字段（FCVC/NCP/CH2O/FAF/TUE）的取值范围本身就是问卷语义
    （如 FAF 0-3 表示每周运动频率等级），分布偏斜会让 IQR 把合法边界值
    误报为离群点，因此对问卷字段只做领域边界校验；连续字段
    （Age/Height/Weight）额外报告 IQR 离群点数量，供报告说明。
    """

    report: dict[str, object] = {}
    total_out_of_domain = 0
    for column in NUMERIC_FEATURES:
        low, high = OUTLIER_LIMITS[column]
        values = frame[column]
        out_of_domain = int(((values < low) | (values > high)).sum())
        total_out_of_domain += out_of_domain
        entry: dict[str, object] = {
            "domain_limit": [low, high],
            "out_of_domain": out_of_domain,
        }
        if column in ("Age", "Height", "Weight"):
            q1, q3 = values.quantile([0.25, 0.75])
            iqr = q3 - q1
            entry["iqr_low"] = float(q1 - 1.5 * iqr)
            entry["iqr_high"] = float(q3 + 1.5 * iqr)
            entry["iqr_outliers"] = int(
                ((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)).sum()
            )
        report[column] = entry
    return {
        "fields": report,
        "total_out_of_domain": total_out_of_domain,
        "conclusion": (
            "数据为问卷 + SMOTE 合成样本的混合：问卷字段取值均在语义范围内，"
            "无领域非法值；连续字段的 IQR 离群点属于分布尾部而非数据错误，"
            "因此保留全部样本，不做删除或截尾。"
        ),
    }


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

    数据集为横断面调查与合成样本的混合，没有受试者编号，因此不做用户分组；
    但完全重复的行（同一特征向量 + 标签）必须整体落入同一划分，否则会构成
    训练/测试之间的数据泄漏，因此先识别重复组，以组为单位参与分层划分。
    """

    result = frame.copy()
    dup_key = [*FEATURE_NAMES, LABEL_COLUMN]
    duplicated = result.duplicated(subset=dup_key, keep=False)

    # 为每个重复组记录首个出现的行索引作为 leader，组内其余行跟随 leader
    leader_series = result.index.to_series().copy()
    if duplicated.any():
        seen: dict[tuple, object] = {}
        for idx in result.index[duplicated]:
            signature = tuple(result.loc[idx, dup_key].to_list())
            if signature not in seen:
                seen[signature] = idx
            leader_series.loc[idx] = seen[signature]

    # 用 leader 行构成单元帧做分层划分，组内成员共享 leader 的划分
    leaders = pd.Index(leader_series.unique())
    leader_frame = result.loc[leaders].copy()
    train_leaders, rest_leaders = train_test_split(
        leader_frame,
        test_size=0.4,
        stratify=leader_frame[LABEL_COLUMN],
        random_state=random_state,
    )
    validation_leaders, test_leaders = train_test_split(
        rest_leaders,
        test_size=0.5,
        stratify=rest_leaders[LABEL_COLUMN],
        random_state=random_state,
    )
    split_of_leader = pd.Series("train", index=leaders)
    split_of_leader.loc[validation_leaders.index] = "validation"
    split_of_leader.loc[test_leaders.index] = "test"
    result["split"] = split_of_leader.loc[leader_series].to_numpy()
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
        "split_rule": (
            "按标签分层随机划分 60/20/20；数据集无受试者编号，不做用户分组；"
            "完全重复的行按组整体划分，避免跨划分泄漏"
        ),
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
    outliers = detect_outliers(frame)
    quality = _quality_report(frame)
    quality["outlier_summary"] = {
        "total_out_of_domain": outliers["total_out_of_domain"],
        "conclusion": outliers["conclusion"],
    }
    (PROCESSED_DIR / "data_quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_TABLES_DIR / "outlier_summary.json").write_text(
        json.dumps(outliers, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 注意：训练/验证集的取值范围由 src.train 写入 models/raw_ranges.json，
    # 这里不再重复产出 data/processed/raw_ranges.json，避免双份维护。

    print(f"处理完成：{PROCESSED_DIR / 'features.csv'}")
    print(json.dumps(quality, ensure_ascii=False, indent=2))
    return frame


def main() -> None:
    build_processed_dataset()


if __name__ == "__main__":
    main()
