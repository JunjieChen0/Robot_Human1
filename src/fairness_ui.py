"""公平性审核页读取冻结实验结果，不在交互中用测试集调参。"""

import json

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
    summary = json.loads((DIRECTORY / "test_summary.json").read_text(encoding="utf-8"))
    overall = pd.read_csv(DIRECTORY / "test_comparison.csv").set_index("model")
    group_metrics = pd.read_csv(DIRECTORY / "test_group_metrics.csv")
    group_counts = pd.read_csv(DIRECTORY / "group_counts.csv")
    baseline, adjusted = overall.loc["baseline"], overall.loc["mitigated"]
    st.subheader("先看整体表现，再看群体差异")
    cols = st.columns(3)
    cols[0].metric("基线平衡准确率", f"{baseline.balanced_accuracy:.2%}")
    performance_change = adjusted.balanced_accuracy - baseline.balanced_accuracy
    fairness_change = adjusted.equalized_odds_difference - baseline.equalized_odds_difference
    cols[1].metric("约束方案平衡准确率", f"{adjusted.balanced_accuracy:.2%}", None if abs(performance_change) < 1e-12 else f"{100 * performance_change:+.2f} 个百分点")
    cols[2].metric("错误率群体差值 EO", f"{adjusted.equalized_odds_difference:.4f}", None if abs(fairness_change) < 1e-12 else f"{fairness_change:+.4f}", delta_color="inverse")
    delta = adjusted.equalized_odds_difference - baseline.equalized_odds_difference
    if abs(delta) < 1e-12:
        st.warning("本次约束方案没有缩小错误率的群体差异。整体成绩高，也不代表两个群体的表现完全一致。")
    else:
        st.write(f"EO 差值相对基线变化 {delta:+.4f}。应结合各组错误数量和整体性能解释，不能只看这一个数字。")
    st.caption("EO 差值 = 两组 TPR 差值与 FPR 差值中的较大者；越小表示这两类错误率越接近。下方筛选只影响展示，全局差值始终根据两组测试记录计算。")

    group = st.selectbox("查看群体", ["全部群体", "女性", "男性"], key="fairness_group")
    view = group_metrics.loc[group_metrics.group.ne("整体")]
    if group != "全部群体":
        view = view.loc[view.group.eq(group)]
    metric_label = st.selectbox("比较指标", list(METRIC_LABELS.values()), key="fairness_metric")
    metric = next(k for k, v in METRIC_LABELS.items() if v == metric_label)
    chart = view[["group", "model", metric]].rename(columns={"group": "群体", "model": "方案", metric: "数值"})
    chart["方案"] = chart["方案"].map(MODEL_LABELS)
    st.bar_chart(chart, x="群体", y="数值", color="方案", stack=False, height=290)
    columns = ["model", "group", "n", "positive", "negative", "balanced_accuracy", "f1", "tpr", "fnr", "fpr", "selection_rate", "fn", "fp"]
    table = view[columns].copy()
    table["model"] = table["model"].map(MODEL_LABELS)
    table = table.rename(columns={"model": "方案", "group": "群体", "n": "样本量", "positive": "正类数", "negative": "负类数", "fn": "漏判数", "fp": "误判数", **METRIC_LABELS})
    st.dataframe(table.round(4), hide_index=True, width="stretch")
    st.write("漏判：标签属于正类，却被判为负类；漏判率的分母是该组所有正类。误判：标签属于负类，却被判为正类；误判率的分母是该组所有负类。两者的分母不同。")
    with st.expander("错误率的不确定性"):
        intervals = view[["model", "group", "tpr_low", "tpr_high", "fpr_low", "fpr_high", "reliability"]].copy()
        intervals["model"] = intervals["model"].map(MODEL_LABELS)
        st.dataframe(intervals.rename(columns={"model": "方案", "group": "群体", "tpr_low": "TPR区间下限", "tpr_high": "TPR区间上限", "fpr_low": "FPR区间下限", "fpr_high": "FPR区间上限", "reliability": "样本提示"}).round(4), hide_index=True)
        st.write("区间为 95% Wilson 区间。某组本次没有错误，也不意味着未来不会出错。正类或负类为空时，相应指标留空；分母少于 30 时提示不稳定。合成样本间的相关性会限制这些区间的可信程度。")

    st.subheader("各组数据是否可比")
    split_names = {"全部数据": "all", "训练集": "train", "验证集": "validation", "测试集": "test"}
    split = st.selectbox("数据范围", list(split_names), index=3, key="fairness_split")
    sample_table = group_counts.loc[group_counts.split.eq(split_names[split])].drop(columns="split")
    st.dataframe(sample_table.rename(columns={"group": "群体", "n": "样本量", "positive": "正类数", "negative": "负类数", "label_rate": "真实正类比例"}).round(4), hide_index=True)
    st.write(f"测试集预测正类比例差值 DP 为 {adjusted.demographic_parity_difference:.4f}。需要同时看真实标签比例；预测正类比例不同，不能直接认定模型不公平。")

    with st.expander("如何选择约束方案"):
        st.write(summary["selection"]["selection_rule"])
        st.caption(f"已固定方案：{summary['selection']['selected']}。界面不提供测试集调参。StandardScaler 只在训练集拟合，两种模型均仅使用 1270 条训练记录。")
        validation = pd.read_csv(DIRECTORY / "validation_comparison.csv")
        st.dataframe(validation[["model", "bound", "balanced_accuracy", "f1", "equalized_odds_difference"]].rename(columns={"model": "方案", "bound": "训练约束上限", "balanced_accuracy": "平衡准确率", "f1": "F1", "equalized_odds_difference": "验证集EO差值"}).round(4), hide_index=True)
        st.write("约束上限控制训练时的目标，不保证验证集或测试集差值也低于同一个数。约束方案采用 Fairlearn 的随机混合预测，主结果固定随机种子 42。")

    st.subheader("这些结果能说明什么")
    st.write("来源是 UCI 544：2111 条记录，约 77% 是 SMOTE 合成数据。性别只记录 Female/Male，不能代表其他性别身份；数据缺少用户编号，重复组虽未跨集合，仍不能排除同一人的相近记录或合成样本相关性。")
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
