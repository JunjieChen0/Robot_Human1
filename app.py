"""WeightTrend Streamlit 交互原型。"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

from src.config import (
    BINARY_FEATURES,
    FIELD_DESCRIPTIONS_ZH,
    FIELD_HELP_ZH,
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
from src.validation import validate_profile, validate_weight_log, warn_outside_training_range


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

# 原型表单采集的字段（不含由模型用训练集中位数填充的 CH2O / TUE）
FORM_FIELDS = tuple(
    column for column in FIELD_DESCRIPTIONS_ZH
    if column not in IMPUTED_NUMERIC_FEATURES
)

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
        font-size: .8rem;
        color: #6b7480;
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
    div[data-testid="stMetricLabel"] p { font-size: .82rem; color: #5b6472; }
    div[data-testid="stMetricValue"] { font-size: 1.45rem; }

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


def render_field(column: str, container, defaults: dict) -> None:
    """按字段类型渲染单个录入控件（数值 / 二分 / 有序 / 名义）。"""

    label = FIELD_DESCRIPTIONS_ZH[column]
    help_text = FIELD_HELP_ZH.get(column)

    if column in FORM_NUMERIC_FEATURES:
        step, fmt = NUMBER_STEPS[column]
        container.number_input(
            label,
            step=step,
            format=fmt,
            key=column,
            value=defaults[column],
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
        index=options.index(defaults[column]),
        help=help_text,
    )


def show_profile_result(result: dict, warnings: list[str], metadata: dict) -> None:
    st.subheader("肥胖等级估计")
    col1, col2, col3 = st.columns(3)
    col1.metric("估计等级", LABEL_NAMES_ZH[result["label"]])
    col2.metric("最高类别概率", f"{result['top_probability']:.1%}")
    col3.metric("最高与第二高差值", f"{result['top_probability'] - result['second_probability']:.1%}")
    st.caption(f"英文标签：{result['label']}。该结果仅表示模型对当前录入的类别估计。")

    table = pd.DataFrame(
        [
            {"等级": LABEL_NAMES_ZH[name], "英文标签": name, "模型估计概率": prob}
            for name, prob in result["by_label"].items()
        ]
    ).sort_values("模型估计概率", ascending=False)

    left, right = st.columns([1.15, 1])
    with left:
        st.dataframe(
            table.style.format({"模型估计概率": "{:.1%}"}),
            hide_index=True,
            width="stretch",
        )
    with right:
        st.bar_chart(table.set_index("等级")["模型估计概率"], y_label="概率")

    if warnings:
        st.warning("当前录入存在训练范围外数值，估计结果需要谨慎理解。")
        for warning in warnings:
            st.caption(f"提示：{warning}")
    else:
        st.success("当前录入的所有数值都处于训练数据范围内。")

    st.subheader("解释反馈")
    st.write(
        "下表是模型整体的特征重要性，不等于某一次估计的因果解释。"
        "等级估计基于横断面调查数据，不能推断个人未来的体重变化。"
    )
    importance = pd.DataFrame(metadata.get("global_feature_importance", []))
    if not importance.empty:
        top = importance.head(8).copy()
        top["说明"] = top["feature"].map(FIELD_DESCRIPTIONS_ZH)
        top["importance"] = top["importance"].map(lambda value: f"{value:.3f}")
        st.dataframe(
            top[["feature", "说明", "importance"]], hide_index=True, width="stretch"
        )
        imputed_labels = "、".join(FIELD_DESCRIPTIONS_ZH[c] for c in IMPUTED_NUMERIC_FEATURES)
        st.caption(f"注：{imputed_labels}不在表单中采集，按训练集中位数填充。")


def show_comparison(previous: dict, current: dict) -> None:
    st.subheader("修改前后对比")
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

    st.subheader("体重趋势与外推")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最新体重", f"{latest['weight_kg']:.1f} kg")
    col2.metric("活动水平", activity)
    col3.metric("每日消耗估算", f"{expenditure:.0f} kcal")
    col4.metric("每日能量差", f"{deficit:+.0f} kcal")
    st.line_chart(chart, x="day", y="weight_kg", color="segment")
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


def render_profile_inputs(defaults: dict) -> None:
    """渲染身体与行为录入字段（按语义分区，作为主表单的一部分）。"""

    st.subheader("① 身体与行为录入")
    imputed_labels = "、".join(FIELD_DESCRIPTIONS_ZH[c] for c in IMPUTED_NUMERIC_FEATURES)
    st.caption(
        f"{imputed_labels}不在表单中采集，模型按训练集中位数填充；"
        "带 ? 的字段可查看详细说明。"
    )

    for title, columns in PROFILE_SECTIONS:
        with st.container(border=True):
            section_title(title)
            for start in range(0, len(columns), 4):
                cols = st.columns(4)
                for column, col in zip(columns[start : start + 4], cols):
                    render_field(column, col, defaults)


def render_weight_log_inputs() -> tuple[pd.DataFrame, float]:
    """渲染体重记录与饮食录入字段（作为主表单的一部分）。"""

    st.subheader("② 体重记录与饮食录入")
    with st.container(border=True):
        section_title(
            "📉 体重记录",
            "日期格式 YYYY-MM-DD；至少两条记录才能分析趋势。",
        )
        log_input = st.data_editor(
            pd.DataFrame(
                [
                    {"date": "2026-09-01", "weight_kg": 72.0},
                    {"date": "2026-09-15", "weight_kg": 71.2},
                    {"date": "2026-10-01", "weight_kg": 70.5},
                ]
            ),
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
        )
        intake = st.number_input(
            "每日摄入热量（kcal）",
            min_value=0.0,
            step=50.0,
            value=1800.0,
            format="%.0f",
            help="用于计算每日能量差（消耗 − 摄入），进而外推未来体重变化。",
        )
    return log_input, intake


def main() -> None:
    st.markdown(PAGE_STYLE, unsafe_allow_html=True)
    st.title("⚖️ 减重趋势分析原型")
    st.caption("录入身高体重、运动与饮食信息，查看肥胖等级估计、体重趋势与能量平衡外推。")
    st.info(
        "课程实验声明：模型概率不是绝对正确率，结果不代表医学诊断、疾病筛查或健康风险结论。"
    )

    with st.expander("📖 使用说明"):
        st.markdown(
            """1. **录入身体与行为信息**：填写年龄、身高、体重、饮食习惯与运动情况；
2. **蔬菜摄入量（1–3 分）**：1 = 很少吃蔬菜，2 = 适量，3 = 每餐都吃较多蔬菜；介于两档之间可填 0.5 的中间值（如 1.5、2.5）；
3. **经常高热量饮食**：高热量食物指油炸食品、甜点、含糖饮料、肥肉等；选「是」表示多数日子都会摄入，选「否」表示偶尔或不常吃；
4. **估计肥胖等级**：提交表单后，页面展示 7 个等级的模型概率分布，以及最高/次高概率差值；
5. **录入体重记录**：在表格中按 `YYYY-MM-DD` 输入至少两条体重记录，并填写每日摄入热量；
6. **查看趋势与外推**：页面绘制记录期体重变化，并按能量平衡模型外推未来 90 天；
7. **理解概率**：模型概率是对当前录入的类别估计，不是绝对正确率，也不是医学诊断；
8. **采集范围**：每日饮水量与电子设备使用时间不在表单中采集，由模型按训练集中位数填充（模型训练时包含这两项，输入维度保持完整）；
9. **适用范围**：模型基于 UCI 544 公开数据集训练，录入值超出训练范围时会给出提示，结果仅用于课程学习。"""
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
        st.stop()

    model = load_model()
    metadata = load_json(str(MODELS_DIR / "model_metadata.json"))
    ranges = load_json(str(MODELS_DIR / "raw_ranges.json"))
    demo_profiles = load_demo_profiles()

    with st.sidebar:
        st.header("🎯 演示档案")
        st.caption("选择一个类别样例，一键载入表单，用于快速演示完整流程。")
        selected = st.selectbox("演示档案", demo_profiles["sample_id"].tolist())
        st.caption("演示档案取自训练集，仅用于展示表单操作流程。")
        if st.button("载入到表单", width="stretch"):
            row = demo_profiles.loc[demo_profiles["sample_id"].eq(selected)].iloc[0]
            for column in FORM_FIELDS:
                st.session_state[column] = row[column]
            st.success("已载入，请查看主页面表单。")

    defaults = default_profile()
    with st.form("main_form"):
        render_profile_inputs(defaults)
        log_input, intake = render_weight_log_inputs()
        st.caption("一次提交即可完成「肥胖等级估计」与「体重趋势分析」。")
        submitted = st.form_submit_button("🔍 估计并分析趋势", type="primary", width="stretch")

    if submitted:
        profile = fill_imputed_features(profile_from_session(), ranges)
        clean, profile_errors = validate_profile(profile)
        log, log_errors, log_warnings = validate_weight_log(log_input)

        for error in profile_errors:
            st.error(error)
        for error in log_errors:
            st.error(error)
        for warning in log_warnings:
            st.warning(warning)

        if not profile_errors:
            st.divider()
            warnings = warn_outside_training_range(clean, ranges)
            result = predict_profile(model, clean)
            previous = st.session_state.get("last_profile_result")
            st.session_state["last_profile_result"] = result
            st.session_state["last_profile_clean"] = clean
            show_profile_result(result, warnings, metadata)
            if previous is not None:
                show_comparison(previous, result)

        if not profile_errors and not log_errors:
            show_trend(log, clean, intake)

    current_result = st.session_state.get("last_profile_result")
    if not submitted and current_result is not None:
        st.divider()
        show_profile_result(
            current_result,
            warn_outside_training_range(
                st.session_state.get("last_profile_clean", {}), ranges
            ),
            metadata,
        )


if __name__ == "__main__":
    main()
