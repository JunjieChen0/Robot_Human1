"""WeightTrend Streamlit 交互原型。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

import altair as alt
import joblib
import pandas as pd
import streamlit as st

from src.config import (
    BINARY_FEATURES,
    FIELD_DESCRIPTIONS_ZH,
    FIELD_HELP_ZH,
    FORM_FIELDS,
    FORM_NUMERIC_FEATURES,
    IMPUTED_NUMERIC_FEATURES,
    LABEL_NAMES_ZH,
    MODELS_DIR,
    NOMINAL_BASELINE,
    NOMINAL_DUMMIES,
    NOMINAL_FEATURE,
    ORDINAL_FEATURES,
    ORDINAL_LEVELS,
    SAMPLE_DIR,
)
from src.energy import activity_level_from_exercise, project_weight, tdee
from src.preprocess import encode_features
from src.profile_io import parse_profile_csv
from src.validation import HARD_LIMITS, validate_profile, validate_weight_log, warn_outside_training_range


st.set_page_config(
    page_title="减重趋势分析",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

NUMBER_STEPS = {
    "Age": (1.0, "%.0f"),
    "Height": (0.01, "%.2f"),
    "Weight": (0.1, "%.1f"),
    "FCVC": (0.5, "%.1f"),
    "NCP": (1.0, "%.0f"),
    "FAF": (0.5, "%.1f"),
}

OPTION_LABELS = {
    "Male": "男性", "Female": "女性", "yes": "是", "no": "否 / 从不",
    "Sometimes": "有时", "Frequently": "经常", "Always": "总是",
    "Automobile": "汽车", "Bike": "自行车", "Motorbike": "摩托车",
    "Public_Transportation": "公共交通", "Walking": "步行",
}

DEMO_LOG = pd.DataFrame([
    {"date": "2026-09-01", "weight_kg": 72.0},
    {"date": "2026-09-15", "weight_kg": 71.2},
    {"date": "2026-10-01", "weight_kg": 70.5},
])

# 表单的视觉分区：按语义分组，保证每行填满、层级清晰
PROFILE_SECTIONS = (
    ("🧍 身体基本信息", ("Age", "Height", "Weight", "Gender")),
    ("🥗 饮食习惯", ("FCVC", "NCP", "FAVC", "SCC", "CAEC", "CALC")),
    (
        "🏃 运动与生活方式",
        ("FAF", NOMINAL_FEATURE, "SMOKE", "family_history_with_overweight"),
    ),
)

_LAYOUT_FIELDS = tuple(
    column for _, columns in PROFILE_SECTIONS for column in columns
)
if set(_LAYOUT_FIELDS) != set(FORM_FIELDS) or len(_LAYOUT_FIELDS) != len(FORM_FIELDS):
    raise ValueError("表单分区字段与采集字段不一致，请检查 PROFILE_SECTIONS。")

PAGE_STYLE = """
<style>
    .block-container { padding-top: 2.0rem; padding-bottom: 3.0rem; }

    /* 分区卡片 */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid #e4e9f2;
        border-radius: 14px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
    }

    /* 分区标题 */
    .wt-section {
        font-size: 1.0rem;
        font-weight: 600;
        color: #1f2a37;
        margin: 0 0 .2rem 0;
    }
    .wt-hint {
        font-size: 1rem;
        color: #465366;
        margin: 0 0 .9rem 0;
        line-height: 1.5;
    }

    /* 指标卡 */
    div[data-testid="stMetric"] {
        background: #f7f9fc;
        border: 1px solid #e4e9f2;
        border-radius: 12px;
        padding: 14px 16px;
    }
    div[data-testid="stMetricLabel"] p { font-size: 1rem; color: #465366; }
    div[data-testid="stMetricValue"] { font-size: 1.45rem; }
    div[data-testid="stMetric"] { color: #1f2a37; }
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {
        font-size: 1rem !important;
        color: #465366 !important;
        opacity: 1 !important;
    }
    h2[id], h3[id] { scroll-margin-top: 5rem; }
    [data-testid="stCaptionContainer"] a { color: #174ea6 !important; text-decoration: underline; }
    button[kind^="primary"] {
        background: #174ea6 !important;
        border-color: #174ea6 !important;
        color: #ffffff !important;
    }
    button { min-height: 44px !important; }
    button:focus-visible, input:focus-visible, textarea:focus-visible, a:focus-visible,
    [role="combobox"]:focus-visible {
        outline: 3px solid #174ea6 !important;
        outline-offset: 3px;
    }

    /* 侧边栏 */
    section[data-testid="stSidebar"] { background: #f7f9fc; }
    section[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
</style>
"""


@st.cache_resource
def load_model():
    model_path = MODELS_DIR / "final_model.joblib"
    if not model_path.is_file():
        raise FileNotFoundError("尚未找到模型，请先运行 python -m src.train。")
    return joblib.load(model_path)


@st.cache_data
def load_json(path_string: str) -> dict:
    return json.loads(Path(path_string).read_text(encoding="utf-8"))


@st.cache_data
def load_demo_profiles() -> pd.DataFrame:
    return pd.read_csv(SAMPLE_DIR / "demo_profiles.csv")


def default_profile() -> dict:
    """表单默认值，只包含原型实际采集的字段。"""

    return {
        **{column: 25.0 if column == "Age" else 1.7 if column == "Height" else 70.0
           for column in ("Age", "Height", "Weight")},
        "FCVC": 2.0,
        "NCP": 3.0,
        "FAF": 1.0,
        "Gender": "Female",
        **{column: "no" for column in BINARY_FEATURES if column != "Gender"},
        **{column: "Sometimes" for column in ORDINAL_FEATURES},
        NOMINAL_FEATURE: NOMINAL_BASELINE,
    }


def profile_from_session() -> dict:
    """读取原型表单实际采集的字段。"""

    return {column: st.session_state[column] for column in FORM_FIELDS}


def fill_imputed_features(profile: dict, ranges: dict) -> dict:
    """用训练集中位数补齐原型未采集的字段，保证模型输入为完整的 19 维特征。"""

    filled = dict(profile)
    for column in IMPUTED_NUMERIC_FEATURES:
        filled[column] = float(ranges[column]["median"])
    return filled


def predict_profile(model, clean: dict) -> dict:
    frame = encode_features(pd.DataFrame([clean]))
    label = str(model.predict(frame)[0])
    probabilities = model.predict_proba(frame)[0]
    classes = [str(item) for item in model.named_steps["classifier"].classes_]
    by_label = {name: float(prob) for name, prob in zip(classes, probabilities)}
    ranked = sorted(by_label.items(), key=lambda item: item[1], reverse=True)
    return {
        "label": label,
        "by_label": by_label,
        "top_probability": ranked[0][1],
        "second_probability": ranked[1][1] if len(ranked) > 1 else 0.0,
    }


def section_title(title: str, hint: str | None = None) -> None:
    """渲染分区标题与说明。"""

    st.markdown(f'<p class="wt-section">{title}</p>', unsafe_allow_html=True)
    if hint:
        st.markdown(f'<p class="wt-hint">{hint}</p>', unsafe_allow_html=True)


def render_field(column: str, container) -> None:
    """按字段类型渲染单个录入控件（数值 / 二分 / 有序 / 名义）。"""

    label = FIELD_DESCRIPTIONS_ZH[column]
    help_text = FIELD_HELP_ZH.get(column)

    if column in FORM_NUMERIC_FEATURES:
        step, fmt = NUMBER_STEPS[column]
        container.number_input(
            label,
            min_value=HARD_LIMITS[column][0],
            max_value=HARD_LIMITS[column][1],
            step=step,
            format=fmt,
            key=column,
            value=None,
            help=help_text,
        )
        return

    if column == "Gender":
        options = ["Male", "Female"]
    elif column in BINARY_FEATURES:
        options = ["no", "yes"]
    elif column in ORDINAL_FEATURES:
        options = list(ORDINAL_LEVELS)
    elif column == NOMINAL_FEATURE:
        options = [NOMINAL_BASELINE, *NOMINAL_DUMMIES]
    else:
        raise KeyError(f"未知字段：{column}")

    container.selectbox(
        label,
        options,
        key=column,
        index=None,
        help=help_text,
        format_func=lambda value: ("从不" if column in ORDINAL_FEATURES else "否") if value == "no" else OPTION_LABELS.get(value, value),
    )


def show_analysis_summary(analysis: dict) -> None:
    st.subheader("本次结果摘要", anchor="result-summary")
    clean, result = analysis["clean"], analysis["result"]
    valid_trend = analysis["include_trend"] and not analysis["log_errors"]
    cols = st.columns(3)
    cols[0].metric("本次分类结论", LABEL_NAMES_ZH[result["label"]])
    cols[1].metric("分类采用档案体重", f"{clean['Weight']:.1f} kg")
    cols[2].metric("趋势采用日志体重", f"{analysis['log'].iloc[-1]['weight_kg']:.1f} kg" if valid_trend else "未生成" if analysis["include_trend"] else "未启用")
    st.write("先看分类结论与体重来源，再看下方概率及解释。分类估计的是肥胖等级，不是综合健康评分或诊断。")
    if valid_trend:
        first, latest = analysis["log"].iloc[0], analysis["log"].iloc[-1]
        st.write(f"日志变化：{first['weight_kg']:.1f} → {latest['weight_kg']:.1f} kg，合计 {latest['weight_kg'] - first['weight_kg']:+.1f} kg；来源：{analysis['log_source']}。")
        st.info("档案体重用于分类，日志最新体重用于趋势起点；仅修改档案体重不会同步修改日志。未来曲线假设每日能量差恒定，是外推参考。")
    elif analysis["include_trend"]:
        st.warning("本次分类已生成，趋势未生成。请修正体重记录或摄入热量后重新分析，也可取消趋势分析。")
        st.markdown("[返回每日摄入热量](#daily-intake) · [返回体重记录](#weight-log)")
    else:
        st.caption("本次仅分析肥胖等级，未启用体重趋势。")
    links = ["[查看分类概率与解释](#classification)", "[填写用户反馈](#user-feedback)", "[修改档案](#profile-input)"]
    if valid_trend:
        links.insert(1, "[查看体重趋势](#trend-result)")
    st.markdown(" · ".join(links))


def show_profile_result(result: dict, warnings: list[str], metadata: dict, clean: dict) -> None:
    st.subheader("肥胖等级估计", anchor="classification")
    col1, col2, col3 = st.columns(3)
    col1.metric("估计等级", LABEL_NAMES_ZH[result["label"]])
    col2.metric("最高类别概率", f"{result['top_probability']:.1%}")
    col3.metric("最高与第二高差值", f"{result['top_probability'] - result['second_probability']:.1%}")
    st.caption(f"英文标签：{result['label']}。该结果仅表示模型对当前录入的类别估计。")
    st.info(
        "如何理解：七分类结果估计的是当前输入所属的肥胖等级，不是综合健康评分。"
        "例如某类概率为 80%，不等于个人有 80% 的患病风险，也不代表模型有 80% 的正确率。"
        "未验证对中国大学生或其他新群体的适用性。"
    )
    st.caption(
        f"分类档案体重 {clean['Weight']:.1f} kg，身高 {clean['Height']:.2f} m，"
        f"年龄 {clean['Age']:.0f} 岁，运动频率评分 {clean['FAF']:g}。"
        "类别概率未经校准，不表示减重成功率。"
    )
    st.caption("未经校准：尚未验证模型报出 80% 的一批记录是否约有 80% 分类正确，因此不能把显示概率当作保证。")

    table = pd.DataFrame(
        [
            {"等级": LABEL_NAMES_ZH[name], "英文标签": name, "模型估计概率": prob}
            for name, prob in result["by_label"].items()
        ]
    ).sort_values("模型估计概率", ascending=False)
    leaders = table.iloc[:2]
    st.info(
        f"前两类：{leaders.iloc[0]['等级']} {leaders.iloc[0]['模型估计概率']:.1%}、"
        f"{leaders.iloc[1]['等级']} {leaders.iloc[1]['模型估计概率']:.1%}，"
        f"相差 {(result['top_probability'] - result['second_probability']) * 100:.1f} 个百分点。"
        "两类概率越接近，分类越容易随输入变化，请同时查看两类结果，谨慎理解单一标签。"
    )

    left, right = st.columns([1.15, 1])
    with left:
        st.dataframe(
            table.style.format({"模型估计概率": "{:.1%}"}),
            hide_index=True,
            width="stretch",
        )
    with right:
        probability_chart = alt.Chart(table).mark_bar(color="#174ea6").encode(
            x=alt.X("模型估计概率:Q", title="模型估计概率（%）", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("等级:N", sort=table["等级"].tolist(), title=None, axis=alt.Axis(labelLimit=160)),
            tooltip=["等级:N", alt.Tooltip("模型估计概率:Q", format=".1%")],
        ).properties(height=260, description="七类肥胖等级概率，按概率从高到低排列，与左侧表格顺序一致。").configure_axis(
            labelColor="#465366", titleColor="#465366", labelFontSize=14, titleFontSize=14,
        )
        st.altair_chart(probability_chart, width="stretch", key="probability_chart")

    if warnings:
        st.warning("当前录入存在训练范围外数值，估计结果需要谨慎理解。")
        for warning in warnings:
            st.caption(f"提示：{warning}")
    else:
        st.caption("当前录入的所有数值都处于训练数据范围内；这不能保证分类正确或适用于新群体。")

    st.subheader("解释反馈")
    st.write(
        "下表说明模型在整体分类时相对依赖哪些信息，数值越大表示相对作用越大。"
        "它不解释你个人为什么得到这个结果，也不说明某项习惯会导致肥胖。"
        "例如重要性 0.326 不代表个人有 32.6% 的患病风险。"
    )
    st.caption("横断面调查：记录不同人在某段时期的情况，并非对同一个人长期随访，因此不能据此推断个人未来体重。")
    importance = pd.DataFrame(metadata.get("global_feature_importance", []))
    if not importance.empty:
        top = importance.head(8).copy()
        top["说明"] = top["feature"].map(FIELD_DESCRIPTIONS_ZH)
        top["importance"] = top["importance"].map(lambda value: f"{value:.3f}")
        st.dataframe(
            top[["说明", "importance"]].rename(columns={"说明": "指标", "importance": "整体重要性（相对值）"}),
            hide_index=True, width="stretch",
        )
        imputed_labels = "、".join(FIELD_DESCRIPTIONS_ZH[c] for c in IMPUTED_NUMERIC_FEATURES)
        st.caption(f"注：{imputed_labels}不在表单中采集，按训练集中位数填充。中位数是将训练数值按大小排序后居中的值，不代表你的实际情况。")


def show_comparison(previous_analysis: dict, current_analysis: dict) -> None:
    previous, current = previous_analysis["result"], current_analysis["result"]
    before, after = previous_analysis["clean"], current_analysis["clean"]
    st.subheader("修改前后对比", anchor="analysis-comparison")
    st.caption(
        f"上一次成功提交：{previous_analysis['time']}；本次成功提交：{current_analysis['time']}（北京时间）。"
        "比较的是最近两次成功分析；每次重新分析成功都会更新比较基准，失败不会替换。"
    )
    if previous["label"] == current["label"]:
        st.info(f"分类未改变：{LABEL_NAMES_ZH[current['label']]}；最高类别概率 {previous['top_probability']:.1%} → {current['top_probability']:.1%}。")
    else:
        st.info(f"分类已改变：{LABEL_NAMES_ZH[previous['label']]} → {LABEL_NAMES_ZH[current['label']]}。")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "项目": "估计等级",
                    "修改前": LABEL_NAMES_ZH[previous["label"]],
                    "修改后": LABEL_NAMES_ZH[current["label"]],
                },
                {
                    "项目": "最高类别概率",
                    "修改前": f"{previous['top_probability']:.1%}",
                    "修改后": f"{current['top_probability']:.1%}",
                },
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    changes = [
        {"输入字段": FIELD_DESCRIPTIONS_ZH[name],
         "修改前": str(OPTION_LABELS.get(before[name], before[name])),
         "修改后": str(OPTION_LABELS.get(after[name], after[name]))}
        for name in FORM_FIELDS if before[name] != after[name]
    ]
    if changes:
        st.write(f"已修改 {len(changes)} 项档案输入：" + "、".join(item["输入字段"] for item in changes))
        st.dataframe(pd.DataFrame(changes), hide_index=True, width="stretch")
    else:
        st.caption("分类档案未改变；体重日志与热量只影响独立的趋势模块。")
    st.caption("对比反映模型对输入的响应，不能证明改变某项习惯会导致该结果。")


def show_trend(log: pd.DataFrame, clean: dict, intake: float) -> None:
    male = clean["Gender"] == "Male"
    latest = log.iloc[-1]
    first = log.iloc[0]
    activity = activity_level_from_exercise(clean["FAF"])
    expenditure = tdee(latest["weight_kg"], clean["Height"], clean["Age"], male, activity)
    deficit = expenditure - intake

    recorded = log.copy()
    recorded["day"] = (recorded["date"] - first["date"]).dt.days.astype(float)
    recorded["segment"] = "记录"
    projection = project_weight(latest["weight_kg"], intake, expenditure, 90)
    projected = pd.DataFrame(projection)
    projected["day"] = projected["day"] + recorded["day"].max()
    projected["segment"] = "外推"
    chart = pd.concat(
        [recorded[["day", "weight_kg", "segment"]], projected[["day", "weight_kg", "segment"]]]
    )

    st.subheader("体重趋势与外推", anchor="trend-result")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最新体重", f"{latest['weight_kg']:.1f} kg")
    col2.metric("活动水平", activity)
    col3.metric("每日消耗估算", f"{expenditure:.0f} kcal")
    col4.metric("每日能量差", f"{deficit:+.0f} kcal")
    st.caption("每日能量差 = 消耗 − 摄入；正值对应能量缺口，负值对应能量盈余。")
    if abs(latest["weight_kg"] - clean["Weight"]) > 0.05:
        st.info("趋势从日志中的最新体重起算，与分类档案体重不同；如需一致，请修改相应输入后重新提交。")
    chart = chart.rename(columns={"day": "天数", "weight_kg": "体重（kg）", "segment": "类型"})
    base = alt.Chart(chart).encode(
        x=alt.X("天数:Q", title="天数（从首条记录起）", axis=alt.Axis(tickMinStep=1, tickCount=7)),
        y=alt.Y("体重（kg）:Q", title="体重（kg）", scale=alt.Scale(zero=False)),
        color=alt.Color("类型:N", scale=alt.Scale(domain=["记录", "外推"], range=["#174ea6", "#a63e00"]), legend=alt.Legend(title="数据类型", orient="top")),
        tooltip=["类型:N", alt.Tooltip("天数:Q", format=".0f"), alt.Tooltip("体重（kg）:Q", format=".1f")],
    )
    lines = base.mark_line(strokeWidth=3).encode(
        strokeDash=alt.StrokeDash("类型:N", scale=alt.Scale(domain=["记录", "外推"], range=[[1, 0], [7, 5]]), legend=alt.Legend(title="数据类型", orient="top")),
    )
    points = base.transform_filter(alt.datum["类型"] == "记录").mark_point(filled=True, size=60)
    boundary = alt.Chart(pd.DataFrame({"天数": [recorded["day"].max()], "说明": ["外推起点"]}))
    rule = boundary.mark_rule(color="#465366", strokeDash=[3, 3]).encode(x="天数:Q", tooltip=["说明:N"])
    label = boundary.mark_text(align="left", baseline="top", dx=6, dy=6, color="#465366").encode(x="天数:Q", y=alt.value(0), text="说明:N")
    trend_chart = (lines + points + rule + label).properties(
        height=320, description="体重记录为实线和圆点，外推为虚线，竖向标记表示外推起点。",
    ).configure_axis(labelColor="#465366", titleColor="#465366", labelFontSize=14, titleFontSize=14).configure_legend(
        labelColor="#465366", titleColor="#465366", labelFontSize=14, titleFontSize=14,
    )
    st.altair_chart(trend_chart, width="stretch", key="trend_chart")
    st.caption(f"第 {recorded['day'].max():.0f} 天（{latest['date']:%Y-%m-%d}）为外推起点。实线与圆点表示记录，虚线表示外推，竖向标记区分两部分。")
    with st.expander("趋势数据表（图表的文字替代）"):
        st.caption(f"第 0 天对应 {first['date']:%Y-%m-%d}；记录与外推通过文字列区分。")
        st.dataframe(chart, hide_index=True)
    span_days = max(int((latest["date"] - first["date"]).days), 1)
    slope_week = (latest["weight_kg"] - first["weight_kg"]) / span_days * 7
    st.caption(
        f"记录期 {span_days} 天，实际变化约 {slope_week:+.2f} kg/周；"
        f"按当前能量差外推约 {-deficit * 7 / 7700:+.2f} kg/周（7700 kcal 折合 1 kg）。"
    )
    st.warning(
        "外推假设每日能量差恒定，未考虑水分波动和代谢适应，仅用于趋势参考；"
        "不作为医学诊断、疾病筛查或治疗建议。"
    )


def render_profile_inputs() -> None:
    """渲染身体与行为录入字段（按语义分区，作为主表单的一部分）。"""

    st.subheader("① 身体与行为录入", anchor="profile-input")
    imputed_labels = "、".join(FIELD_DESCRIPTIONS_ZH[c] for c in IMPUTED_NUMERIC_FEATURES)
    st.caption(
        f"{imputed_labels}不在表单中采集，模型按训练集中位数填充；"
        "带 ? 的字段可查看详细说明。"
    )
    st.caption("性别字段受训练数据限制，仅有女性/男性编码，不能代表全部性别身份。不愿提供时可使用演示档案体验。")

    for title, columns in PROFILE_SECTIONS:
        with st.container(border=True):
            section_title(title)
            for start in range(0, len(columns), 4):
                cols = st.columns(4)
                for column, col in zip(columns[start : start + 4], cols):
                    render_field(column, col)


def render_weight_log_inputs() -> tuple[pd.DataFrame, float]:
    """渲染体重记录与饮食录入字段（作为主表单的一部分）。"""

    st.subheader("② 体重记录与饮食录入（可选）", anchor="weight-log")
    with st.container(border=True):
        section_title(
            "📉 体重记录",
            "日期格式 YYYY-MM-DD；至少两条记录才能分析趋势。",
        )
        st.radio("体重记录来源", ["模拟记录（仅演示）", "用户自报记录"], key="log_source", horizontal=True)
        st.caption("初始记录为模拟数据。换成自己的记录后请选择“用户自报记录”。档案体重用于分类，日志最新体重用于趋势。")
        if "weight_log_editor" not in st.session_state:
            st.session_state["weight_log_base"] = st.session_state.get("weight_log_draft", DEMO_LOG)
        log_input = st.data_editor(
            st.session_state["weight_log_base"],
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            key="weight_log_editor",
            column_config={
                "date": st.column_config.TextColumn("日期（YYYY-MM-DD）", required=True),
                "weight_kg": st.column_config.NumberColumn("体重（kg）", min_value=0.1, required=True),
            },
        )
        st.subheader("每日饮食输入", anchor="daily-intake")
        if "daily_intake" not in st.session_state:
            st.session_state["daily_intake"] = 1800.0
        intake = st.number_input(
            "每日摄入热量（kcal）",
            min_value=0.0,
            step=50.0,
            value=None,
            format="%.0f",
            help="用于计算每日能量差（消耗 − 摄入），进而外推未来体重变化。",
            key="daily_intake",
        )
        st.session_state["weight_log_draft"] = log_input.copy()
    return log_input, intake


def render_import(ranges: dict) -> None:
    st.subheader("选择录入方式", anchor="data-entry")
    st.write("**直接填写：** 使用下方中文表单，无需准备文件。**已有 CSV：** 展开下面的导入区，一次载入档案。")
    st.markdown("填写示例：身高 **1.70 米**，体重 **70 千克**。 [直接填写身体与行为信息](#profile-input)")
    with st.expander("导入个人档案（CSV）"):
        st.write("下载模板，保留英文表头与一行数据，使用 UTF-8 CSV，最大 1 MB。身高单位为米，体重单位为 kg。")
        st.caption("类别使用模板中的英文编码；缺失项需补齐。CH2O、TUE 始终按训练中位数填充，额外列不参与导入。")
        with st.expander("查看 CSV 类别编码对照"):
            category_options = {
                **{name: ["no", "yes"] for name in BINARY_FEATURES},
                "Gender": ["Female", "Male"],
                **{name: list(ORDINAL_LEVELS) for name in ORDINAL_FEATURES},
                NOMINAL_FEATURE: [NOMINAL_BASELINE, *NOMINAL_DUMMIES],
            }
            mapping = []
            for name, options in category_options.items():
                pairs = [f"{value} → {'从不' if name in ORDINAL_FEATURES and value == 'no' else '否' if value == 'no' else OPTION_LABELS[value]}" for value in options]
                mapping.append({"CSV 列名": name, "中文字段": FIELD_DESCRIPTIONS_ZH[name], "编码与中文选项": "；".join(pairs)})
            st.dataframe(pd.DataFrame(mapping), hide_index=True, width="stretch")
        st.download_button(
            "下载档案模板", pd.DataFrame([default_profile()])[list(FORM_FIELDS)].to_csv(index=False).encode("utf-8-sig"),
            "profile_template.csv", "text/csv", on_click="ignore",
        )
        uploaded = st.file_uploader("选择个人档案 CSV", type=["csv"], key="profile_upload")
        if st.button("校验并载入档案", disabled=uploaded is None, key="import_profile"):
            profile, errors, notices = parse_profile_csv(uploaded.getvalue(), ranges)
            for error in errors:
                st.error(error)
            for notice in notices:
                st.info(notice)
            if not errors:
                for name, value in profile.items():
                    st.session_state[name] = value
                st.session_state["profile_origin"] = (
                    "CSV 与示例模板一致（仅作示例展示，请核对来源）"
                    if profile == default_profile() else "CSV 导入（用户提供，真实性未核验）"
                )
                st.session_state["origin_profile"] = profile
                st.success("校验通过，已载入表单。请核对后点击“估计并分析趋势”。")


def render_feedback(analysis: dict) -> None:
    st.subheader("④ 理解自测与用户反馈", anchor="user-feedback")
    st.caption("反馈仅保存在当前浏览器会话。请勿填写姓名、学号或联系方式；下载后可交给测试组织者。")
    with st.form("feedback_form"):
        ease = st.radio("操作容易程度（1 很困难，5 很容易）", [1, 2, 3, 4, 5], index=None, horizontal=True, key="feedback_ease")
        answer = st.radio(
            "当前分类结果表示什么？",
            ["根据当前输入估计的肥胖等级", "个人综合健康评分", "未来 90 天的实际体重"],
            index=None, key="result_quiz",
        )
        comment = st.text_area("遇到的问题或改进建议（可选）", max_chars=1000, key="feedback_comment")
        sent = st.form_submit_button("保存本次反馈", type="primary")
    if sent:
        if ease is None or answer is None:
            st.error("请选择操作容易程度，并完成一道理解题；已填写内容会保留。")
        else:
            correct = answer == "根据当前输入估计的肥胖等级"
            st.session_state["saved_feedback"] = {
                "analysis_time": analysis["time"], "feedback_time": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
                "ease_1_to_5": ease, "answer": answer, "understood_classification": correct,
                "comment": comment,
            }
            st.success("反馈已保存在当前会话。下一步：点击下方“下载匿名反馈（JSON）”，将文件交给测试组织者。")
            if correct:
                st.success("理解正确：分类估计、记录趋势和未来外推属于不同结果。")
            else:
                st.warning("请再看结果说明：分类估计的是当前输入的肥胖等级，不代表综合健康或未来体重。")
    saved = st.session_state.get("saved_feedback")
    if saved:
        st.caption(f"已保存反馈对应的分析时间：{saved['analysis_time']}。新结果需要重新提交反馈。")
        st.download_button("下载匿名反馈（JSON）", json.dumps(saved, ensure_ascii=False, indent=2), "weighttrend_feedback.json", "application/json", on_click="ignore")


def main() -> None:
    st.markdown(PAGE_STYLE, unsafe_allow_html=True)
    page = st.sidebar.radio("页面", ["体重管理原型", "模型公平性审核", "模型判断"], key="main_page")
    if page == "模型判断":
        from src.model_judgment_ui import render_model_judgment_page

        render_model_judgment_page()
        return
    if page == "模型公平性审核":
        from src.fairness_ui import render_fairness_page

        render_fairness_page()
        return
    st.title("⚖️ WeightTrend · 体重状态与趋势")
    st.caption("录入身高体重、运动与饮食信息，查看肥胖等级估计、体重趋势与能量平衡外推。")
    st.caption("面向大学生的课堂实验 · ① 输入数据 → ② 查看概览 → ③ 分析与解释 → ④ 反馈或修改重算")
    st.info(
        "课程实验声明：模型概率不是绝对正确率，结果不代表医学诊断、疾病筛查或健康风险结论。"
    )

    with st.expander("📖 使用说明"):
        st.markdown(
            """1. **录入身体与行为信息**：填写年龄、身高、体重、饮食习惯与运动情况；
2. **蔬菜摄入评分（1–3）**：1 = 很少吃蔬菜，2 = 适量，3 = 每餐都吃较多蔬菜；介于两档之间可填 0.5 的中间值（如 1.5、2.5）；
3. **经常高热量饮食**：高热量食物指油炸食品、甜点、含糖饮料、肥肉等；选「是」表示多数日子都会摄入，选「否」表示偶尔或不常吃；
4. **估计肥胖等级**：提交表单后，页面展示 7 个等级的模型概率分布，以及最高/次高概率差值；
5. **录入体重记录**：在表格中按 `YYYY-MM-DD` 输入至少两条体重记录，并填写每日摄入热量；
6. **查看趋势与外推**：页面绘制记录期体重变化，并按能量平衡模型外推未来 90 天；
7. **理解概率**：模型概率是对当前录入的类别估计，不是绝对正确率，也不是医学诊断；
8. **采集范围**：每日饮水量与电子设备使用时间不在表单中采集，由模型按训练集中位数填充（模型训练时包含这两项，输入维度保持完整）；
9. **适用范围**：模型基于 UCI 544 公开数据集训练，录入值超出训练范围时会给出提示，结果仅用于课程学习。"""
        )

    with st.expander("数据来源与适用范围"):
        st.markdown(
            "训练数据来自 [UCI 544 肥胖等级数据集]"
            "(https://archive.ics.uci.edu/dataset/544/estimation+of+obesity+levels+based+on+eating+habits+and+physical+condition)，"
            "共 2111 条记录、16 个特征，涉及墨西哥、秘鲁和哥伦比亚；"
            "约 23% 为直接采集记录，77% 为 SMOTE 合成记录，许可为 CC BY 4.0。"
        )
        st.caption("SMOTE：根据已有样本生成相似的新记录，并非新增真人调查；合成记录不代表已验证真实新用户的使用效果。")
        st.write(
            "本原型用于课程中的体重管理演示，尚未验证对其他国家、年龄层或特殊生理状况人群的适用性。"
            "饮水量和屏幕时间按训练集中位数填充。等级分类与能量平衡外推是两个独立模块，"
            "分类成绩不能证明未来体重预测准确。"
        )

    required_paths = [
        MODELS_DIR / "final_model.joblib",
        MODELS_DIR / "model_metadata.json",
        MODELS_DIR / "raw_ranges.json",
        SAMPLE_DIR / "demo_profiles.csv",
    ]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        st.error("原型所需文件尚未生成：" + ", ".join(missing))
        st.code("python -m src.preprocess\npython -m src.train\npython -m src.evaluate")
        if st.button("检查文件并重试", key="retry_missing_files"):
            st.rerun()
        st.stop()

    try:
        with st.spinner("正在读取模型与演示资料…"):
            model = load_model()
            metadata = load_json(str(MODELS_DIR / "model_metadata.json"))
            ranges = load_json(str(MODELS_DIR / "raw_ranges.json"))
            demo_profiles = load_demo_profiles()
    except Exception:
        st.error("模型或资料加载失败。请检查文件及依赖版本，再重试。")
        st.code("python -m src.train\npython -m src.evaluate")
        if st.button("重新加载模型", key="reload_model"):
            st.cache_resource.clear()
            st.cache_data.clear()
            st.rerun()
        return

    for name, value in st.session_state.get("profile_draft", {}).items():
        if name not in st.session_state:
            st.session_state[name] = value
    for name, value in st.session_state.get("controls_draft", {}).items():
        if name not in st.session_state:
            st.session_state[name] = value

    with st.sidebar:
        st.header("🎯 演示档案")
        st.caption("选择一个类别样例，一键载入表单，用于快速演示完整流程。")
        selected = st.selectbox("演示档案", demo_profiles["sample_id"].tolist())
        st.caption("演示档案取自训练集，仅用于展示表单操作流程。")
        if st.button("载入到表单", width="stretch"):
            row = demo_profiles.loc[demo_profiles["sample_id"].eq(selected)].iloc[0]
            for column in FORM_FIELDS:
                st.session_state[column] = row[column]
            st.session_state["profile_origin"] = "训练集演示档案（非个人健康记录）"
            st.session_state["origin_profile"] = {column: row[column] for column in FORM_FIELDS}
            st.success("已载入，请查看主页面表单。")
        st.write("键盘操作：Tab / Shift+Tab 移动焦点，方向键选择选项，Enter 或空格激活按钮。")
        st.caption("档案、结果与反馈仅保留在会话中；刷新或关闭可能丢失，请先下载所需反馈。")

    defaults = default_profile()
    for name, value in defaults.items():
        if name not in st.session_state:
            st.session_state[name] = value
    render_import(ranges)
    render_profile_inputs()
    profile = profile_from_session()
    st.session_state["profile_draft"] = profile
    origin = st.session_state.get("profile_origin", "默认示例（模拟，非个人记录）")
    if profile != st.session_state.get("origin_profile", defaults):
        origin = "用户编辑（可能包含默认或演示值，请逐项核对）"
    if "include_trend" not in st.session_state:
        st.session_state["include_trend"] = True
    include_trend = st.checkbox("同时分析体重趋势（可选）", key="include_trend")
    log_input, intake = pd.DataFrame(columns=["date", "weight_kg"]), 1800.0
    if include_trend:
        log_input, intake = render_weight_log_inputs()
    st.session_state["controls_draft"] = {
        name: st.session_state[name] for name in ("include_trend", "log_source", "daily_intake")
        if name in st.session_state
    }

    st.subheader("当前输入概览")
    st.caption(f"档案来源：{origin}。下方概览随输入更新，模型结果需点击按钮更新。")
    overview = st.columns(3)
    overview[0].metric("档案体重", f"{profile['Weight']:.1f} kg" if profile["Weight"] is not None else "未填写")
    overview[1].metric("身高", f"{profile['Height']:.2f} m" if profile["Height"] is not None else "未填写")
    overview[2].metric("运动频率评分", f"{profile['FAF']:g} / 3" if profile["FAF"] is not None else "未填写")
    last = st.session_state.get("last_analysis")
    log_source = st.session_state.get("log_source", "模拟记录（仅演示）")
    changed = last is not None and (
        profile != {name: last["clean"][name] for name in FORM_FIELDS}
        or include_trend != last["include_trend"]
        or (include_trend and (not log_input.equals(last["log_input"]) or intake != last["intake"] or log_source != last["log_source"]))
        or origin != last["origin"]
    )
    input_status = st.empty()
    if changed:
        input_status.warning("输入已修改，请重新分析。下方仍为上次提交的结果，不对应当前编辑内容。")
    elif last is None:
        input_status.info("尚无分析结果。请核对默认示例或录入自己的档案，再点击下方按钮。没有体重记录时可取消趋势分析。")
    submitted = st.button("🔍 估计并分析趋势", type="primary", width="stretch", key="analyze")

    if submitted:
        clean, profile_errors = validate_profile(fill_imputed_features(profile, ranges))
        log, log_errors, log_warnings = validate_weight_log(log_input) if include_trend else (log_input, [], [])
        if include_trend and (intake is None or not isfinite(intake) or intake <= 0):
            log_errors.append("每日摄入热量：请输入大于 0 的热量值（kcal），例如 1800，再重新分析。")

        for error in profile_errors:
            st.error(error)
        for error in log_errors:
            st.error(error)
        if log_errors:
            st.markdown("[返回每日摄入热量](#daily-intake) · [返回体重记录](#weight-log)")
        for warning in log_warnings:
            st.warning(warning)

        if not profile_errors:
            try:
                with st.spinner("正在校验输入并运行七分类模型…"):
                    result = predict_profile(model, clean)
            except Exception:
                st.error("本次分析失败，已保留输入和上次成功结果。请检查模型及依赖，或修改输入后点击“估计并分析趋势”重试。")
            else:
                input_status.empty()
                st.session_state["previous_analysis"] = last
                st.session_state["last_analysis"] = {
                    "result": result, "clean": clean, "log": log, "log_input": log_input.copy(),
                    "intake": intake, "log_source": log_source, "include_trend": include_trend,
                    "origin": origin, "log_errors": log_errors, "log_warnings": log_warnings,
                    "time": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="milliseconds"),
                }
                if log_errors:
                    st.warning("本次仅完成分类，趋势未生成。请按错误提示修正后重新分析，或取消趋势分析。")
                else:
                    st.success("分类分析已完成。结果与解释见下方。")

    current = st.session_state.get("last_analysis")
    if current is not None:
        st.divider()
        st.subheader("③ 分析结果与解释")
        st.info(f"上次提交：{current['time']}。结果采用该次快照；修改输入后请点击“估计并分析趋势”更新。")
        st.caption(f"分类档案来源：{current['origin']}；体重记录来源：{current['log_source'] if current['include_trend'] else '未启用趋势'}。")
        show_analysis_summary(current)
        previous = st.session_state.get("previous_analysis")
        if previous:
            show_comparison(previous, current)
        show_profile_result(
            current["result"], warn_outside_training_range(current["clean"], ranges), metadata, current["clean"],
        )
        if current["include_trend"]:
            if current["log_errors"]:
                st.warning("该次趋势未生成：" + "；".join(current["log_errors"]) + " 可修改记录后重试，或取消趋势分析。")
            else:
                show_trend(current["log"], current["clean"], current["intake"])
                for warning in current["log_warnings"]:
                    st.warning(warning)
        render_feedback(current)


if __name__ == "__main__":
    main()
