"""测试集错误案例分析：错误分布、特征对比与典型错误案例。

读取 evaluate 产出的 test_predictions.csv，生成 Markdown 分析报告，
供实验报告引用错误样本的分布与可能原因。
"""

from __future__ import annotations

import pandas as pd

from src.config import (
    FIELD_DESCRIPTIONS_ZH,
    LABEL_COLUMN,
    LABEL_NAMES_ZH,
    NUMERIC_FEATURES,
    PROCESSED_DIR,
    REPORT_TABLES_DIR,
)


def _label_zh(label: str) -> str:
    return LABEL_NAMES_ZH.get(label, label)


def _confusion_error_table(errors: pd.DataFrame) -> pd.DataFrame:
    """按 (真实标签, 预测标签) 统计错误样本数。"""

    return (
        errors.groupby([LABEL_COLUMN, "predicted"], sort=False)
        .size()
        .rename("count")
        .reset_index()
        .sort_values("count", ascending=False)
    )


def _feature_profile(frame: pd.DataFrame, indices, title: str) -> pd.Series:
    """计算指定行在数值特征上的均值。"""

    return frame.loc[indices, NUMERIC_FEATURES].mean().rename(title)


def build_error_analysis() -> str:
    data_path = PROCESSED_DIR / "features.csv"
    predictions_path = REPORT_TABLES_DIR / "test_predictions.csv"
    if not data_path.is_file() or not predictions_path.is_file():
        raise FileNotFoundError("请先运行完整流水线（preprocess/train/evaluate）。")

    frame = pd.read_csv(data_path)
    test_frame = frame[frame["split"].eq("test")].copy().reset_index(drop=True)
    predictions = pd.read_csv(predictions_path)
    predictions["error"] = predictions[LABEL_COLUMN] != predictions["predicted"]

    errors = predictions[predictions["error"]].copy()
    correct = predictions[~predictions["error"]].copy()

    lines = ["# 错误案例分析", ""]
    lines.append(f"- 测试集样本数：{len(predictions)}")
    lines.append(f"- 错误样本数：{len(errors)}（错误率 {len(errors) / len(predictions):.1%}）")
    lines.append("")

    # 1. 错误分布
    lines.append("## 1. 错误分布（真实标签 × 预测标签）")
    lines.append("")
    error_table = _confusion_error_table(errors)
    lines.append("| 真实标签 | 预测标签 | 错误数 |")
    lines.append("|---|---|---:|")
    for _, row in error_table.iterrows():
        lines.append(
            f"| {_label_zh(row[LABEL_COLUMN])} | {_label_zh(row['predicted'])} | {int(row['count'])} |"
        )
    lines.append("")

    # 2. 特征对比
    lines.append("## 2. 错误样本与正确样本的特征均值对比")
    lines.append("")
    err_profile = _feature_profile(test_frame, errors.index, "错误样本")
    ok_profile = _feature_profile(test_frame, correct.index, "正确样本")
    compare = pd.concat([ok_profile, err_profile], axis=1)
    compare["差异"] = compare["错误样本"] - compare["正确样本"]
    lines.append("| 特征 | 正确样本均值 | 错误样本均值 | 差异 |")
    lines.append("|---|---:|---:|---:|")
    for column in NUMERIC_FEATURES:
        lines.append(
            f"| {FIELD_DESCRIPTIONS_ZH[column]} | {compare.loc[column, '正确样本']:.3f} "
            f"| {compare.loc[column, '错误样本']:.3f} | {compare.loc[column, '差异']:+.3f} |"
        )
    lines.append("")

    # 3. 典型错误案例
    lines.append("## 3. 典型错误案例（按最高类别概率排序）")
    lines.append("")
    lines.append("以下列出模型最“自信”却仍然判错的样本，用于说明错误集中出现的场景。")
    lines.append("")
    error_with_prob = errors.copy()
    probability_columns = [
        column for column in error_with_prob.columns if column.startswith("prob_")
    ]
    error_with_prob["top_prob"] = error_with_prob[probability_columns].max(axis=1)
    error_with_prob["second_prob"] = error_with_prob[probability_columns].apply(
        lambda row: float(row.nlargest(2).iloc[-1]) if len(row) >= 2 else 0.0,
        axis=1,
    )
    top_errors = error_with_prob.nlargest(5, "top_prob")
    lines.append("| 真实标签 | 预测标签 | 最高概率 | 次高概率 | 差值 |")
    lines.append("|---|---|---:|---:|---:|")
    for _, row in top_errors.iterrows():
        lines.append(
            f"| {_label_zh(row[LABEL_COLUMN])} | {_label_zh(row['predicted'])} "
            f"| {row['top_prob']:.1%} | {row['second_prob']:.1%} | {row['top_prob'] - row['second_prob']:.1%} |"
        )
    lines.append("")

    # 4. 数据驱动的观察
    lines.append("## 4. 数据驱动的观察")
    lines.append("")
    if len(errors) > 0:
        worst_true = errors[LABEL_COLUMN].value_counts().idxmax()
        lines.append(
            f"- 错误最多的真实类别：{_label_zh(worst_true)}"
            f"（{int((errors[LABEL_COLUMN] == worst_true).sum())} 条）"
        )
        lines.append(
            f"- 错误样本与正确样本的体重均值差为 {compare.loc['Weight', '差异']:+.3f} kg。"
            "两组类别构成不同，不能将均值差解释为误判原因；不同单位字段也不能据此比较重要性。"
        )
        mid_prob_share = float(
            error_with_prob["top_prob"].between(0.4, 0.7).mean()
        )
        lines.append(
            f"- 约 {mid_prob_share:.0%} 的错误样本最高概率落在 40%–70% 区间，"
            "这一比例只描述错误子集，不能据此推断该概率区间的总体错误率。"
        )
    lines.append("")
    lines.append("### 可能原因（供实验报告引用）")
    lines.append("")
    lines.append("- 相邻等级的错误较多（如正常体重与超重 I 级），可能与类别边界附近的特征组合重叠有关，仍需逐例检查。")
    lines.append("- 数据为问卷 + SMOTE 合成样本的混合，合成部分的边界模式可能不完全反映真实人群，导致边界样本易混淆。")
    lines.append("- 概率分布平坦：最高概率与次高概率接近时，类别归属本身不确定，轻微特征变化即可改变预测。")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    REPORT_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    content = build_error_analysis()
    output = REPORT_TABLES_DIR / "error_analysis.md"
    output.write_text(content, encoding="utf-8")
    print(f"错误案例分析已写入：{output}")


if __name__ == "__main__":
    main()
