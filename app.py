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
    LABEL_NAMES_ZH,
    MODELS_DIR,
    NOMINAL_BASELINE,
    NOMINAL_DUMMIES,
    NOMINAL_FEATURE,
    NUMERIC_FEATURES,
    ORDINAL_FEATURES,
    ORDINAL_LEVELS,
    SAMPLE_DIR,
)
from src.energy import activity_level_from_exercise, project_weight, tdee
from src.preprocess import encode_features
from src.validation import validate_profile, validate_weight_log, warn_outside_training_range


st.set_page_config(page_title="减重趋势分析", page_icon="⚖️", layout="wide")

NUMBER_STEPS = {
    "Age": (1.0, "%.0f"),
    "Height": (0.01, "%.2f"),
    "Weight": (0.1, "%.1f"),
    "FCVC": (0.5, "%.1f"),
    "NCP": (1.0, "%.0f"),
    "CH2O": (0.5, "%.1f"),
    "FAF": (0.5, "%.1f"),
    "TUE": (0.5, "%.1f"),
}


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
    return {
        **{column: 25.0 if column == "Age" else 1.7 if column == "Height" else 70.0
           for column in ("Age", "Height", "Weight")},
        "FCVC": 2.0,
        "NCP": 3.0,
        "CH2O": 2.0,
        "FAF": 1.0,
        "TUE": 1.0,
        "Gender": "Female",
        **{column: "no" for column in BINARY_FEATURES if column != "Gender"},
        **{column: "Sometimes" for column in ORDINAL_FEATURES},
        NOMINAL_FEATURE: NOMINAL_BASELINE,
    }


def profile_from_session() -> dict:
    return {column: st.session_state[column] for column in FIELD_DESCRIPTIONS_ZH}


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
    st.dataframe(
        table.style.format({"模型估计概率": "{:.1%}"}), hide_index=True, width="stretch"
    )
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


def main() -> None:
    st.title("⚖️ 减重趋势分析原型")
    st.write("录入身高体重、运动与饮食信息，查看肥胖等级估计、体重趋势和能量平衡外推。")
    st.info(
        "课程实验声明：模型概率不是绝对正确率，结果不代表医学诊断、疾病筛查或健康风险结论。"
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

    st.sidebar.header("演示档案")
    selected = st.sidebar.selectbox("选择演示档案", demo_profiles["sample_id"].tolist())
    if st.sidebar.button("载入到表单"):
        row = demo_profiles.loc[demo_profiles["sample_id"].eq(selected)].iloc[0]
        for column in FIELD_DESCRIPTIONS_ZH:
            st.session_state[column] = row[column]
        st.sidebar.caption("已载入，回到主页面查看表单。")

    defaults = default_profile()
    with st.form("profile_form"):
        st.subheader("身体与行为录入")
        for start in range(0, len(NUMERIC_FEATURES), 4):
            cols = st.columns(4)
            for column, col in zip(NUMERIC_FEATURES[start : start + 4], cols):
                step, fmt = NUMBER_STEPS[column]
                col.number_input(
                    FIELD_DESCRIPTIONS_ZH[column],
                    step=step,
                    format=fmt,
                    key=column,
                    value=defaults[column],
                )
        for start in range(0, len(BINARY_FEATURES), 4):
            cols = st.columns(4)
            for column, col in zip(BINARY_FEATURES[start : start + 4], cols):
                options = ["Male", "Female"] if column == "Gender" else ["no", "yes"]
                col.selectbox(
                    FIELD_DESCRIPTIONS_ZH[column],
                    options,
                    key=column,
                    index=options.index(defaults[column]),
                )
        cols = st.columns(4)
        for column, col in zip(ORDINAL_FEATURES, cols):
            options = list(ORDINAL_LEVELS)
            col.selectbox(
                FIELD_DESCRIPTIONS_ZH[column],
                options,
                key=column,
                index=options.index(defaults[column]),
            )
        cols[2].selectbox(
            FIELD_DESCRIPTIONS_ZH[NOMINAL_FEATURE],
            [NOMINAL_BASELINE, *NOMINAL_DUMMIES],
            key=NOMINAL_FEATURE,
            index=0,
        )
        submitted = st.form_submit_button("估计 / 重新估计", type="primary")

    if submitted:
        clean, errors = validate_profile(profile_from_session())
        if errors:
            for error in errors:
                st.error(error)
        else:
            warnings = warn_outside_training_range(clean, ranges)
            result = predict_profile(model, clean)
            previous = st.session_state.get("last_profile_result")
            st.session_state["last_profile_result"] = result
            st.session_state["last_profile_clean"] = clean
            show_profile_result(result, warnings, metadata)
            if previous is not None:
                show_comparison(previous, result)

    current_result = st.session_state.get("last_profile_result")
    if not submitted and current_result is not None:
        show_profile_result(
            current_result,
            warn_outside_training_range(
                st.session_state.get("last_profile_clean", {}), ranges
            ),
            metadata,
        )

    st.divider()
    clean = st.session_state.get("last_profile_clean", default_profile())
    with st.form("trend_form"):
        st.subheader("体重记录与饮食录入")
        st.caption("日期格式 YYYY-MM-DD；至少两条记录才能分析趋势。")
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
        )
        submitted_trend = st.form_submit_button("分析趋势", type="primary")

    if submitted_trend:
        log, log_errors, log_warnings = validate_weight_log(log_input)
        for error in log_errors:
            st.error(error)
        for warning in log_warnings:
            st.warning(warning)
        if not log_errors:
            show_trend(log, clean, intake)


if __name__ == "__main__":
    main()
