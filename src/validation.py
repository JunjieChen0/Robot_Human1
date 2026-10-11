"""原型录入校验函数。"""

from __future__ import annotations

from math import isfinite
from typing import Any

import pandas as pd

from src.config import (
    BINARY_FEATURES,
    FIELD_DESCRIPTIONS_ZH,
    NOMINAL_BASELINE,
    NOMINAL_DUMMIES,
    NOMINAL_FEATURE,
    NUMERIC_FEATURES,
    ORDINAL_FEATURES,
    ORDINAL_LEVELS,
)


HARD_LIMITS = {
    "Age": (10.0, 100.0),
    "Height": (1.0, 2.5),
    "Weight": (20.0, 300.0),
    "FCVC": (1.0, 3.0),
    "NCP": (1.0, 4.0),
    "CH2O": (0.0, 10.0),
    "FAF": (0.0, 3.0),
    "TUE": (0.0, 24.0),
}
BINARY_VALUES = {"yes", "no"}
GENDER_VALUES = {"Male", "Female"}
NOMINAL_VALUES = {NOMINAL_BASELINE, *NOMINAL_DUMMIES}


def _label(column: str) -> str:
    return FIELD_DESCRIPTIONS_ZH.get(column, column)


def validate_profile(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """校验一份原始问卷录入，返回清洗后的录入和错误信息。"""

    errors: list[str] = []
    clean: dict[str, Any] = {}
    for column in NUMERIC_FEATURES:
        try:
            value = float(row.get(column))
        except (TypeError, ValueError):
            errors.append(f"{_label(column)} 不是数值。")
            continue
        low, high = HARD_LIMITS[column]
        if not low <= value <= high:
            errors.append(f"{_label(column)} 超出合理范围 {low:g}–{high:g}。")
        clean[column] = value
    for column in BINARY_FEATURES:
        allowed = GENDER_VALUES if column == "Gender" else BINARY_VALUES
        if row.get(column) not in allowed:
            errors.append(
                f"{column}（{_label(column)}）取值必须是 {' / '.join(sorted(allowed))}。"
            )
        clean[column] = row.get(column)
    for column in ORDINAL_FEATURES:
        if row.get(column) not in ORDINAL_LEVELS:
            errors.append(
                f"{column}（{_label(column)}）取值必须是 {' / '.join(ORDINAL_LEVELS)}。"
            )
        clean[column] = row.get(column)
    if row.get(NOMINAL_FEATURE) not in NOMINAL_VALUES:
        errors.append(
            f"{NOMINAL_FEATURE}（{_label(NOMINAL_FEATURE)}）取值必须是 "
            f"{' / '.join(sorted(NOMINAL_VALUES))}。"
        )
    clean[NOMINAL_FEATURE] = row.get(NOMINAL_FEATURE)
    return clean, errors


def warn_outside_training_range(clean: dict[str, Any], ranges: dict[str, dict[str, float]]) -> list[str]:
    """训练范围之外的数值只产生警告：极端值可能合法但模型覆盖不足。"""

    warnings = []
    for column in NUMERIC_FEATURES:
        info = ranges.get(column, {})
        if column not in clean or not info:
            continue
        low, high = float(info["min"]), float(info["max"])
        if not low <= clean[column] <= high:
            warnings.append(
                f"{_label(column)} 超出训练数据的 {low:g}–{high:g} 范围，估计结果可靠性可能降低。"
            )
    return warnings


def _blank_row_mask(frame: pd.DataFrame) -> pd.Series:
    """识别 data_editor 动态新增、日期与体重都未填写的空行。"""

    date = frame.get("date")
    weight = pd.to_numeric(frame.get("weight_kg"), errors="coerce")
    date_blank = date.isna() | date.astype(str).str.strip().eq("")
    return date_blank & weight.isna()


def validate_weight_log(frame: pd.DataFrame | None) -> tuple[pd.DataFrame, list[str], list[str]]:
    """校验体重记录表，返回按日期排序的记录、错误和警告。"""

    errors: list[str] = []
    warnings: list[str] = []
    empty = pd.DataFrame(columns=["date", "weight_kg"])
    not_enough = "至少需要 2 条体重记录才能分析趋势。"
    if frame is None or frame.empty:
        return empty, [not_enough], warnings

    # 空白行若参与校验，会同时报出日期与体重两条误导性错误，因此先行丢弃
    filled = frame.loc[~_blank_row_mask(frame)]
    if filled.empty:
        return empty, [not_enough], warnings

    log = pd.DataFrame(
        {
            "date": pd.to_datetime(filled.get("date"), format="%Y-%m-%d", errors="coerce"),
            "weight_kg": pd.to_numeric(filled.get("weight_kg"), errors="coerce"),
        }
    )
    if log["date"].isna().any():
        errors.append("存在无法解析的日期。")
    if log["weight_kg"].isna().any():
        errors.append("存在非数值体重。")
    if not log["weight_kg"].dropna().map(isfinite).all():
        errors.append("体重必须为有限数值。")
    if (log["weight_kg"] <= 0).any():
        errors.append("体重必须为正数。")
    log = log.dropna().sort_values("date").reset_index(drop=True)
    if not errors and len(log) < 2:
        errors.append("至少需要 2 条体重记录才能分析趋势。")
    if not errors and log["date"].duplicated().any():
        warnings.append("存在同一天的多条记录，绘图时保留排序后的全部记录。")
    return log, errors, warnings
