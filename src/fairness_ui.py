"""公平性审核页读取冻结实验结果，不在交互中用测试集调参。"""

import json

import altair as alt
import pandas as pd
import streamlit as st

from src.config import REPORTS_DIR


DIRECTORY = REPORTS_DIR / "fairness"
MODEL_LABELS = {"baseline": "基线模型", "mitigated": "公平性约束方案"}
METRIC_LABELS = {
    "balanced_accuracy": "平衡准确率", "f1": "F1", "tpr": "识别率 TPR",
    "fnr": "漏判率 FNR", "fpr": "误判率 FPR", "selection_rate": "预测正类比例",
}


def render_fairness_page():
    st.title("模型公平性审核")
    st.caption("按数据集记录的性别，比较二分类基线与公平性约束方案。")
    st.info("这里将肥胖 I–III 型标签合并为正类，其余标签为负类。审核的是独立的二分类实验，不是原页面七分类模型或未来体重预测，也不是医疗诊断。")
    required = ["test_summary.json", "test_group_metrics.csv", "test_comparison.csv", "group_counts.csv", "validation_comparison.csv"]
    if any(not (DIRECTORY / name).is_file() for name in required):
        st.warning("公平性实验结果尚未生成。请先运行下面两条命令，再刷新页面。")
        st.code("python -m src.fairness train\npython -m src.fairness evaluate")
        return
    try:
        summary = json.loads((DIRECTORY / "test_summary.json").read_text(encoding="utf-8"))
        overall = pd.read_csv(DIRECTORY / "test_comparison.csv").set_index("model")
        group_metrics = pd.read_csv(DIRECTORY / "test_group_metrics.csv")
        group_counts = pd.read_csv(DIRECTORY / "group_counts.csv")
        validation = pd.read_csv(DIRECTORY / "validation_comparison.csv")
    except (OSError, ValueError, pd.errors.ParserError):
        st.error("审核资料读取失败。请检查 reports/fairness 中的冻结文件，恢复后重试。")
        if st.button("重新读取审核资料", key="reload_fairness"):
            st.rerun()
        return
    baseline, adjusted = overall.loc["baseline"], overall.loc["mitigated"]
    st.subheader("先看整体表现，再看群体差异")
    cols = st.columns(3)
    cols[0].metric("基线平衡准确率", f"{baseline.balanced_accuracy:.2%}")
    performance_change = adjusted.balanced_accuracy - baseline.balanced_accuracy
    fairness_change = adjusted.equalized_odds_difference - baseline.equalized_odds_difference
    cols[1].metric("约束方案平衡准确率", f"{adjusted.balanced_accuracy:.2%}", None if abs(performance_change) < 1e-12 else f"{100 * performance_change:+.2f} 个百分点")
    cols[2].metric("错误率群体差值 EO", f"{adjusted.equalized_odds_difference * 100:.2f} 个百分点", None if abs(fairness_change) < 1e-12 else f"{fairness_change * 100:+.2f} 个百分点", delta_color="inverse")
    st.caption(f"改进前 → 改进后：EO 差值 {baseline.equalized_odds_difference * 100:.2f} → {adjusted.equalized_odds_difference * 100:.2f} 个百分点。顶部卡片始终显示整体测试结果。")
    st.caption(f"当前 EO 原始小数为 {adjusted.equalized_odds_difference:.4f}，即约 {adjusted.equalized_odds_difference * 100:.2f} 个百分点的群体差值，不是个人患病概率。")
    st.write("平衡准确率：分别计算正类和负类的识别率，再取平均；它与普通准确率的计算方法不同。F1：综合考虑预测正类的准确程度和正类找全程度。")
    delta = adjusted.equalized_odds_difference - baseline.equalized_odds_difference
    if abs(delta) < 1e-12:
        st.warning("本次约束方案没有缩小错误率的群体差异。整体成绩高，也不代表两个群体的表现完全一致。")
    else:
        st.write(f"EO 差值相对基线变化 {delta * 100:+.2f} 个百分点。应结合各组错误数量和整体性能解释，不能只看这一个数字。")
    st.caption("EO 差值 = 两组 TPR 差值与 FPR 差值中的较大者；越小表示这两类错误率越接近。下方筛选只影响展示，全局差值始终根据两组测试记录计算。")

    group = st.selectbox("查看群体", ["全部群体", "女性", "男性"], key="fairness_group")
    view = group_metrics.loc[group_metrics.group.ne("整体")]
    if group != "全部群体":
        view = view.loc[view.group.eq(group)]
    metric_label = st.selectbox("比较指标", list(METRIC_LABELS.values()), key="fairness_metric")
    metric = next(k for k, v in METRIC_LABELS.items() if v == metric_label)
    st.caption(f"当前展示：{group} · {metric_label} · 同时比较两方案。筛选影响下方图表、紧邻的分组指标表及区间表；更下方样本统计由“数据范围”独立控制。")
    chart = view[["group", "model", metric]].rename(columns={"group": "群体", "model": "方案", metric: "数值"})
    chart["方案"] = chart["方案"].map(MODEL_LABELS)
    comparison_chart = alt.Chart(chart).mark_bar().encode(
        x=alt.X("数值:Q", title=f"{metric_label}（%）", axis=alt.Axis(format=".2%", tickCount=6), scale=alt.Scale(domainMin=0)),
        y=alt.Y("群体:N", sort=["女性", "男性"], title=None, axis=alt.Axis(labelAngle=0)),
        yOffset=alt.YOffset("方案:N", sort=list(MODEL_LABELS.values())),
        color=alt.Color("方案:N", scale=alt.Scale(domain=list(MODEL_LABELS.values()), range=["#174ea6", "#a63e00"]), legend=alt.Legend(orient="top")),
        tooltip=["群体:N", "方案:N", alt.Tooltip("数值:Q", title=metric_label, format=".2%")],
    ).properties(
        height=240, description=f"分组比较{metric_label}，以百分比展示；具体样本量和错误数见下方表格。",
    ).configure_axis(labelColor="#465366", titleColor="#465366", labelFontSize=14, titleFontSize=14).configure_legend(
        labelColor="#465366", titleColor="#465366", labelFontSize=14, titleFontSize=14,
    )
    st.altair_chart(comparison_chart, width="stretch", key="fairness_chart")
    core_columns = ["model", "group", "n", "fn", "fp", "fnr", "fpr"]
    table = view[core_columns].copy()
    table["model"] = table["model"].map(MODEL_LABELS)
    table = table.rename(columns={"model": "方案", "group": "群体", "n": "样本量", "positive": "正类数", "negative": "负类数", "fn": "漏判数", "fp": "误判数", **METRIC_LABELS})
    st.write("先看样本量、漏判数和误判数，再比较两种错误率；两方案同时列出。")
    st.dataframe(table.style.format({"样本量": "{:.0f}", "漏判数": "{:.0f}", "误判数": "{:.0f}", "漏判率 FNR": "{:.2%}", "误判率 FPR": "{:.2%}"}, na_rep="未定义"), hide_index=True, width="stretch")
    st.write("漏判：标签属于正类，却被判为负类；漏判率的分母是该组所有正类。误判：标签属于负类，却被判为正类；误判率的分母是该组所有负类。两者的分母不同。")
    with st.expander("详细分组指标（含正负类数、F1 与识别率）"):
        columns = ["model", "group", "n", "positive", "negative", "balanced_accuracy", "f1", "tpr", "fnr", "fpr", "selection_rate", "fn", "fp"]
        details = view[columns].copy()
        details["model"] = details["model"].map(MODEL_LABELS)
        details = details.rename(columns={"model": "方案", "group": "群体", "n": "样本量", "positive": "正类数", "negative": "负类数", "fn": "漏判数", "fp": "误判数", **METRIC_LABELS})
        formats = {name: "{:.2%}" for name in METRIC_LABELS.values()}
        formats.update({name: "{:.0f}" for name in ("样本量", "正类数", "负类数", "漏判数", "误判数")})
        st.dataframe(details.style.format(formats, na_rep="未定义"), hide_index=True, width="stretch")
        st.caption("识别率 TPR：该组实际正类中被正确找出的比例。例如 100 条正类中找出 98 条，识别率为 98%，另有 2 条漏判。F1 也按百分比展示。")
    with st.expander("错误率的不确定性"):
        intervals = view[["model", "group", "tpr_low", "tpr_high", "fpr_low", "fpr_high", "reliability"]].copy()
        intervals["model"] = intervals["model"].map(MODEL_LABELS)
        intervals = intervals.rename(columns={"model": "方案", "group": "群体", "tpr_low": "识别率 TPR 下限", "tpr_high": "识别率 TPR 上限", "fpr_low": "误判率 FPR 下限", "fpr_high": "误判率 FPR 上限", "reliability": "样本提示"})
        interval_columns = ["识别率 TPR 下限", "识别率 TPR 上限", "误判率 FPR 下限", "误判率 FPR 上限"]
        st.dataframe(intervals.style.format({name: "{:.2%}" for name in interval_columns}, na_rep="未定义"), hide_index=True, width="stretch")
        st.write("识别率范围：找出实际正类的比例；误判率范围：实际负类被错误判为正类的比例。区间越宽，说明估计越不确定，不是个人患病概率。")
        st.write("95% Wilson 区间是一种根据错误数量和样本量估计统计不确定性的方法。某组本次没有错误，也不意味着未来不会出错。正类或负类为空时，相应指标显示未定义；分母少于 30 时提示不稳定。合成样本间的相关性会限制这些区间的可信程度。")

    st.subheader("各组数据是否可比")
    split_names = {"全部数据": "all", "训练集": "train", "验证集": "validation", "测试集": "test"}
    split = st.selectbox("数据范围", list(split_names), index=3, key="fairness_split")
    sample_table = group_counts.loc[group_counts.split.eq(split_names[split])].drop(columns="split")
    sample_table = sample_table.rename(columns={"group": "群体", "n": "样本量", "positive": "正类数", "negative": "负类数", "label_rate": "真实正类比例"})
    st.dataframe(sample_table.style.format({"样本量": "{:.0f}", "正类数": "{:.0f}", "负类数": "{:.0f}", "真实正类比例": "{:.2%}"}, na_rep="未定义"), hide_index=True)
    st.write(f"测试集预测正类比例差值 DP 为 {adjusted.demographic_parity_difference * 100:.2f} 个百分点。需要同时看真实标签比例；预测正类比例不同，不能直接认定模型不公平。")

    with st.expander("如何选择约束方案"):
        st.write(summary["selection"]["selection_rule"])
        st.caption(f"已固定方案：{summary['selection']['selected']}。界面不提供测试集调参。StandardScaler 只在训练集拟合，两种模型均仅使用 1270 条训练记录。")
        selection_table = validation[["model", "bound", "balanced_accuracy", "f1", "equalized_odds_difference"]].copy()
        selection_table[["bound", "equalized_odds_difference"]] *= 100
        selection_table = selection_table.rename(columns={"model": "方案", "bound": "训练约束上限（百分点）", "balanced_accuracy": "平衡准确率", "f1": "F1", "equalized_odds_difference": "验证集EO差值（百分点）"})
        st.dataframe(selection_table.style.format({"训练约束上限（百分点）": "{:.2f}", "平衡准确率": "{:.2%}", "F1": "{:.2%}", "验证集EO差值（百分点）": "{:.2f}"}, na_rep="不适用"), hide_index=True)
        st.write("约束上限控制训练时的目标，不保证验证集或测试集差值也低于同一个数。约束方案采用 Fairlearn 的随机混合预测，主结果固定随机种子 42。")

    st.subheader("这些结果能说明什么")
    st.write("来源是 UCI 544：2111 条记录，约 77% 是 SMOTE 合成数据。性别只记录 Female/Male，不能代表其他性别身份；数据缺少用户编号，重复组虽未跨集合，仍不能排除同一人的相近记录或合成样本相关性。")
    st.caption("SMOTE：根据已有样本生成相似的新记录，并非新增真人参与者；合成记录不能证明模型在真实新用户身上同样有效。")
    st.write("本次只完成性别审核，未开展年龄或交叉群体审核。体重与身高直接关联肥胖标签，二分类成绩高不代表模型能判断健康状况，更不能证明对其他国家和人群同样可靠。")
    with st.expander("理解自测"):
        answer = st.radio("整体准确率约 99%，能否说明所有群体表现一致？", ["能，整体成绩已经足够", "不能，还要比较各组错误率和样本量"], index=None, key="fairness_quiz")
        if st.button("查看解释", key="fairness_quiz_check"):
            if answer is None:
                st.info("请先选择一个答案。")
            elif answer.startswith("不能"):
                st.success("理解正确。整体指标会把不同群体合并计算，可能掩盖错误集中的情况。")
            else:
                st.warning("还需要查看分组指标。本次女性组零错误、男性组有三个错误，但整体准确率仍很高。")
        st.caption("自测用于帮助理解，不自动作为真人用户测试成绩。")
    st.download_button("下载分组测试结果", (DIRECTORY / "test_group_metrics.csv").read_bytes(), "公平性分组测试结果.csv", "text/csv")
