"""模型判断：置换实验、特征证据和理解任务；仅读取冻结产物。"""

import json

import altair as alt
import pandas as pd
import streamlit as st

from src.config import FEATURE_NAMES, LABEL_NAMES_ZH
from src.model_judgment import FEATURES, OUTPUT, distribution_table, input_dictionary


PAGE_VERSION = "model-judgment-v1"


def importance_chart(importance, selected):
    table = importance.assign(mean_pp=importance.mean_drop * 100,
                              low_pp=importance.low * 100, high_pp=importance.high * 100,
                              std_pp=importance.std_drop * 100)
    pick = alt.selection_point(name="feature_pick", fields=["feature"], toggle=False)
    base = alt.Chart(table).encode(y=alt.Y("label:N", title=None, sort=table.label.tolist(), axis=alt.Axis(labelLimit=180)))
    domain = [min(-.5, float(table.low_pp.min()) - .5), max(.5, float(table.high_pp.max()) + 1)]
    tooltip = [alt.Tooltip("label:N", title="输入"), alt.Tooltip("mean_pp:Q", title="平均下降（百分点）", format=".3f"),
               alt.Tooltip("std_pp:Q", title="标准差（百分点）", format=".3f"), alt.Tooltip("repeats:Q", title="置换次数")]
    bars = base.mark_bar(size=25).encode(
        x=alt.X("mean_pp:Q", title="平衡准确率平均下降（百分点）", scale=alt.Scale(domain=domain)),
        color=alt.condition(alt.datum.feature == selected, alt.value("#174ea6"), alt.value("#92adc4")),
    )
    spread = base.mark_rule(color="#a63e00", strokeWidth=2).encode(x="low_pp:Q", x2="high_pp:Q")
    # 零值也有可点击的点，不因条形宽度为零而无法选择。
    dots = base.mark_point(filled=True, size=85, color="#a63e00").encode(x="mean_pp:Q")
    zero = alt.Chart(pd.DataFrame({"zero": [0]})).mark_rule(color="#465366").encode(x="zero:Q")
    hit = base.mark_bar(size=36, opacity=.001).encode(
        x=alt.datum(domain[0]), x2=alt.datum(domain[1]), tooltip=tooltip).add_params(pick)
    return (bars + spread + dots + zero + hit).properties(height=270, description="五项实际输入的验证集置换重要性。条形为平均下降，橙点及横线为均值加减一标准差，含零值和负值，可点击输入查看证据。").configure_axis(
        labelFontSize=14, titleFontSize=14, labelColor="#465366", titleColor="#465366")


def select_chart_feature():
    selection = st.session_state["judgment_importance"].get("selection", {})
    points = selection.get("feature_pick", [])
    if points:
        st.session_state["judgment_feature"] = points[-1]["feature"]


def render_cases(records, selected):
    st.subheader("一条判对、一条判错：对照实际输入")
    st.write("下面是未打乱输入时的预测。默认各取原 CSV 中行号最小的一条，也可另选记录；这些案例不代表所有正确或错误记录。")
    for column, correct, title in zip(st.columns(2), (True, False), ("预测正确的记录", "预测错误的记录")):
        with column:
            st.write(f"**{title}**")
            pool = records.loc[records.correct.eq(correct)]
            if pool.empty:
                st.info("本批记录没有此类案例，不生成虚构案例。")
                continue
            row_id = st.selectbox("原始 CSV 行号（含表头）", pool.source_csv_row.tolist(), key=f"judgment_case_{correct}")
            row = pool.loc[pool.source_csv_row.eq(row_id)].iloc[0]
            st.write(f"真实标签：**{LABEL_NAMES_ZH[row.true_label]}**")
            st.write(f"模型输出：**{LABEL_NAMES_ZH[row.predicted_label]}**")
            st.write(f"选中输入 {FEATURES[selected][0]}：**{row[selected]:.6g} {FEATURES[selected][1]}**")
            st.caption(f"最高类别概率 {row.top_probability:.1%}，未经校准；标签不是医学诊断。")
            inputs = input_dictionary()
            inputs["输入值"] = [f"{row[name]:.4g}" for name in FEATURE_NAMES]
            inputs["定位"] = ["当前选中特征" if name == selected else "" for name in FEATURE_NAMES]
            st.dataframe(inputs[["定位", "输入列", "含义", "输入值", "单位或编码", "当前来源"]], hide_index=True, width="stretch")
            st.caption("完整输入表显示4位有效数字，下载的验证记录CSV保留计算时的数值精度。")
    st.warning("整批重要性不能解释单条记录为何这样分类。并列案例仅让你核对输入、真实标签和预测；本页没有计算局部归因，也不能判断个人患病原因。")


def render_tasks(summary):
    st.subheader("理解任务：先记录回答，再查看解释")
    st.caption("供同学独立操作。仅在当前会话暂存，下载后交给组织者；不采集姓名或学号。自动测试不算真人测试。")
    with st.form("judgment_tasks"):
        participant = st.text_input("匿名编号（如 J01）", max_chars=20, key="judgment_participant")
        ranking = st.text_input("任务1：指出打乱哪项输入后，模型表现下降最多；写出图中证据。", key="judgment_ranking")
        causality = st.text_area("任务2：这张图能否用于判断个人患病原因？请说明理由。", max_chars=1000, key="judgment_causality")
        issue = st.text_area("误读、困惑或操作问题（可选；保留原话）", max_chars=1000, key="judgment_issue")
        sent = st.form_submit_button("保存首次回答", disabled=bool(st.session_state.get("judgment_response")))
        if sent and not st.session_state.get("judgment_response"):
            if not participant.strip() or not ranking.strip() or not causality.strip():
                st.error("请填写匿名编号及两项任务回答，已填内容会保留。")
            else:
                st.session_state["judgment_response"] = {"page_version": PAGE_VERSION, "participant": participant,
                    "task_1": ranking, "task_2": causality, "issues": issue,
                    "experiment_model_sha256": summary["model_sha256"],
                    "record_type": "参与者自报回答，需组织者核对，未自动判分"}
                st.success("回答已保存，请先下载；组织者另行记录提示次数、误读与后续复测。")
    if st.session_state.get("judgment_response"):
        st.caption("首次回答已锁定；补充说明与提示后回答请另存记录，避免覆盖原话。下一位参与者请使用新的浏览器会话。")
        st.download_button("下载本次回答（JSON）", json.dumps(st.session_state["judgment_response"], ensure_ascii=False, indent=2),
                           "model_judgment_response.json", "application/json", on_click="ignore")
        with st.expander("已记录回答，查看解释"):
            st.write("任务1比较的是平均下降，不是横线最长或数值本身最大。任务2不能判断个人病因：这是固定模型在一批验证记录上的依赖实验，没有证明因果，也没有解释单条记录。")


def render_model_judgment_page():
    st.title("模型判断")
    st.write("模型使用了哪些数据？哪些输入被打乱后，整批预测表现下降较多？")
    required = ("summary.json", "feature_importance.csv", "validation_records.csv", "permutation_repeats.csv", "feature_importance.png")
    if any(not (OUTPUT / name).is_file() for name in required):
        st.warning("模型判断实验尚未生成。先准备处理数据，再运行下方命令。")
        st.code("python -m src.download_data\npython -m src.preprocess\npython -m src.model_judgment")
        return
    try:
        summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
        importance = pd.read_csv(OUTPUT / "feature_importance.csv")
        records = pd.read_csv(OUTPUT / "validation_records.csv")
    except (OSError, ValueError, pd.errors.ParserError):
        st.error("实验文件读取失败，请重新生成模型判断实验后刷新。")
        return
    st.info(f"本页是七分类验证实验：随机森林只用 {summary['train_samples']} 条训练记录学习，在未参与拟合的 {len(records)} 条验证记录上评价。与分类页同算法、同参数；分类页最终模型另用了训练加验证数据重拟合，本图不直接解释那个模型实例。")
    st.caption("来源：UCI 544，共2111条问卷与合成记录，约77%为SMOTE合成。这里的样本量是记录数，不是参与人数；本页不用测试集，不评价未来体重，也不作医学诊断。")
    with st.expander("模型实际收到的全部19列输入与编码"):
        st.dataframe(input_dictionary(), hide_index=True, width="stretch")
        st.write(f"表单采集14项，出行方式展开为4列；饮水量CH2O={summary['imputed_values']['CH2O']:.4g}、设备使用TUE={summary['imputed_values']['TUE']:.4g}按训练中位数补齐。BMI不是独立模型输入。")

    st.subheader("五项输入被打乱后，验证集表现平均下降多少？")
    st.write(f"未打乱时平衡准确率为 **{summary['baseline_score']:.2%}**。它是七个真实类别各自召回率的平均值。固定同一模型，每次仅随机打乱一列，每项重复 **{summary['repeats']}次**。")
    st.caption("条形=平均下降；橙点和横线=均值±1标准差，表示重复打乱的波动，不是置信区间。单位为百分点（0.01=1个百分点）；保留零值和负值。")
    st.session_state.setdefault("judgment_feature", str(importance.iloc[0].feature))
    st.altair_chart(importance_chart(importance, st.session_state["judgment_feature"]), width="stretch",
                   key="judgment_importance", on_select=select_chart_feature, selection_mode="feature_pick")
    st.write("下降越多，说明本实验模型在这批记录上越依赖该输入。零值表示本次未测到下降；负值表示打乱后反而略有提高，不能据此说该输入有害。相关输入可能相互替代，打乱也可能产生不常见组合。")
    st.caption("只比较预先选定的五项代表性输入，不能断言未展示的输入不重要，也不能把排名当作健康建议。")
    with st.expander("查看每项的精确实验分数"):
        table = importance[["label", "mean_drop", "std_drop"]].copy()
        table[["mean_drop", "std_drop"]] *= 100
        table["打乱后平均平衡准确率"] = summary["baseline_score"] - importance.mean_drop
        st.dataframe(table.rename(columns={"label": "输入", "mean_drop": "平均下降（百分点）", "std_drop": "标准差（百分点）"}).style.format(
            {"平均下降（百分点）": "{:.3f}", "标准差（百分点）": "{:.3f}", "打乱后平均平衡准确率": "{:.2%}"}), hide_index=True, width="stretch")

    selected = st.selectbox("点击图中条形或橙点查看证据，也可在此选择", list(FEATURES), format_func=lambda name: FEATURES[name][0], key="judgment_feature")
    label, unit, meaning = FEATURES[selected]
    st.subheader(f"输入证据：{label}")
    st.write(f"**{selected} · {unit}**。{meaning}")
    st.caption(f"以下分布与置换实验使用同一批{len(records)}条验证记录、相同填充口径，不是训练集或你个人的健康记录。")
    if selected == "CH2O":
        st.info("这列在当前验证输入中全为训练中位数，打乱常量不会改变任何输入，所以重要性为零。这不说明饮水对健康不重要，也不表示原始问卷中的饮水值都相同。")
    if selected == "FAF":
        n = int(records.FAF.gt(0).sum())
        st.write(f"运动频率评分大于0：{n}/{len(records)}条（{n / len(records):.1%}）。这不是“近期参加体育活动人数”，问卷没有相应时间窗。")
    distribution = distribution_table(records, selected)
    chart = alt.Chart(distribution).mark_bar(color="#174ea6").encode(
        x=alt.X("区间:N", sort=distribution["区间"].tolist(), title=f"{label}（{unit}）", axis=alt.Axis(labelAngle=-25)),
        y=alt.Y("样本量:Q", title="验证记录数"), tooltip=["区间:N", "样本量:Q", alt.Tooltip("占比:Q", format=".1%")],
    ).properties(height=230, description=f"{label}的验证集输入分布，共{len(records)}条记录").configure_axis(
        labelFontSize=14, titleFontSize=14, labelColor="#465366", titleColor="#465366")
    st.altair_chart(chart, width="stretch", key="judgment_distribution")
    st.dataframe(distribution.style.format({"占比": "{:.1%}"}), hide_index=True, width="stretch")
    render_cases(records, selected)
    render_tasks(summary)
    with st.expander("下载图表、实验数据与复现信息"):
        st.caption(f"页面版本：{PAGE_VERSION}；随机种子{summary['seed']}；全流程命令见README。点击或筛选只改变展示，不重训、不重算。")
        for name in ("feature_importance.png", "feature_importance.csv", "permutation_repeats.csv", "validation_records.csv", "summary.json"):
            st.download_button(f"下载 {name}", (OUTPUT / name).read_bytes(), name, on_click="ignore")
