"""原型端到端冒烟测试：用 Streamlit AppTest 无头运行 app.py。

这类测试能捕获"只在提交表单后才暴露"的错误——例如函数返回值未接收导致的
NameError（迭代 7 曾出现：render_weight_log_inputs() 的返回值漏接）。
仅做冒烟检查，不校验具体预测数值。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def build_app() -> AppTest:
    return AppTest.from_file(str(APP_PATH), default_timeout=180)


def find_button(app: AppTest, keyword: str):
    matches = [button for button in app.button if keyword in button.label]
    assert matches, f"未找到包含“{keyword}”的按钮"
    return matches[0]


def test_app_loads_without_exception():
    app = build_app().run()
    assert not app.exception
    find_button(app, "估计并分析趋势")


def test_submit_form_runs_prediction_and_trend():
    app = build_app()
    app.run()
    find_button(app, "估计").click().run()

    assert not app.exception
    metric_labels = [metric.label for metric in app.metric]
    # 等级估计区
    assert "估计等级" in metric_labels
    assert "最高类别概率" in metric_labels
    assert "最高与第二高差值" in metric_labels
    # 趋势与外推区（说明体重记录校验与能量平衡计算都成功执行）
    assert "最新体重" in metric_labels
    assert "每日能量差" in metric_labels
    probability, trend = [json.loads(item.proto.spec) for item in app.get("vega_lite_chart")]
    assert probability["encoding"]["x"]["axis"]["format"] == ".0%"
    probability_table = next(item.value for item in app.dataframe if "模型估计概率" in item.value)
    assert probability["encoding"]["y"]["sort"] == probability_table["等级"].tolist()
    assert trend["layer"][0]["encoding"]["strokeDash"]["scale"]["range"] == [[1, 0], [7, 5]]
    assert any(layer.get("mark", {}).get("type") == "rule" for layer in trend["layer"])
    assert any("外推起点" in item.value and "虚线" in item.value for item in app.caption)
    assert any("两类概率越接近" in item.value for item in app.info)


def test_load_demo_profile_runs_without_exception():
    app = build_app()
    app.run()
    find_button(app, "载入到表单").click().run()
    assert not app.exception


def test_saved_result_explains_submission_and_data_source():
    app = build_app().run()
    assert "数据来源与适用范围" in [item.label for item in app.expander]
    find_button(app, "估计").click().run()
    find_button(app, "载入到表单").click().run()
    assert not app.exception
    assert any("上次提交" in item.value for item in app.info)
    assert any("分类档案体重" in item.value for item in app.caption)


def test_edit_marks_result_stale_and_reanalysis_compares_snapshots():
    app = build_app().run()
    app.button(key="analyze").click().run()
    first_time = app.session_state["last_analysis"]["time"]
    app.number_input(key="Weight").set_value(80.0).run()
    assert not app.exception
    assert any("输入已修改" in item.value for item in app.warning)
    assert app.session_state["last_analysis"]["clean"]["Weight"] == 70.0
    assert next(metric.value for metric in app.metric if metric.label == "分类采用档案体重") == "70.0 kg"
    assert next(metric.value for metric in app.metric if metric.label == "趋势采用日志体重") == "70.5 kg"
    app.button(key="analyze").click().run()
    assert app.session_state["last_analysis"]["clean"]["Weight"] == 80.0
    assert app.session_state["previous_analysis"]["clean"]["Weight"] == 70.0
    assert next(metric.value for metric in app.metric if metric.label == "分类采用档案体重") == "80.0 kg"
    assert next(metric.value for metric in app.metric if metric.label == "趋势采用日志体重") == "70.5 kg"
    assert "修改前后对比" in [item.value for item in app.subheader]
    second_time = app.session_state["last_analysis"]["time"]
    assert any(first_time in item.value and second_time in item.value for item in app.caption)
    app.number_input(key="Weight").set_value(75.0).run()
    app.button(key="analyze").click().run()
    assert app.session_state["previous_analysis"]["time"] == second_time
    assert app.session_state["previous_analysis"]["clean"]["Weight"] == 80.0


def test_feedback_keeps_trend_and_links_to_analyzed_snapshot():
    app = build_app().run()
    app.button(key="analyze").click().run()
    analysis_time = app.session_state["last_analysis"]["time"]
    app.radio(key="feedback_ease").set_value(4)
    app.radio(key="result_quiz").set_value("根据当前输入估计的肥胖等级")
    app.text_area(key="feedback_comment").set_value("图表容易理解")
    find_button(app, "保存本次反馈").click().run()
    assert not app.exception
    assert "每日能量差" in [item.label for item in app.metric]
    feedback = app.session_state["saved_feedback"]
    assert feedback["analysis_time"] == analysis_time
    assert feedback["understood_classification"] is True
    assert feedback["comment"] == "图表容易理解"


def test_invalid_trend_can_be_recovered_without_blocking_classification():
    app = build_app().run()
    app.number_input(key="daily_intake").set_value(0.0)
    app.button(key="analyze").click().run()
    assert not app.exception
    assert "估计等级" in [item.label for item in app.metric]
    assert "每日能量差" not in [item.label for item in app.metric]
    assert any("热量" in item.value for item in app.error)
    assert any("请输入大于 0" in item.value for item in app.error)
    assert any("本次仅完成分类，趋势未生成" in item.value for item in app.warning)
    assert not any("分类分析已完成" in item.value for item in app.success)
    app.number_input(key="daily_intake").set_value(1800.0)
    app.button(key="analyze").click().run()
    assert "每日能量差" in [item.label for item in app.metric]


@pytest.mark.parametrize("include_trend", [False, True])
def test_trend_is_optional_and_profile_draft_survives_audit_navigation(include_trend, caplog):
    app = build_app().run()
    app.number_input(key="Weight").set_value(81.0).run()
    app.number_input(key="daily_intake").set_value(1850.0).run()
    app.checkbox(key="include_trend").set_value(include_trend).run()
    app.button(key="analyze").click().run()
    assert not app.exception
    assert "估计等级" in [item.label for item in app.metric]
    assert app.session_state["last_analysis"]["include_trend"] is include_trend
    analysis_time = app.session_state["last_analysis"]["time"]
    with patch("streamlit.elements.lib.policies._shown_default_value_warning", False):
        app.radio(key="main_page").set_value("模型公平性审核").run()
        app.radio(key="main_page").set_value("体重管理原型").run()
    assert not app.exception
    assert app.number_input(key="Weight").value == 81.0
    assert app.checkbox(key="include_trend").value is include_trend
    assert app.session_state["last_analysis"]["time"] == analysis_time
    assert not any("输入已修改" in item.value for item in app.warning)
    assert "was created with a default value" not in caplog.text
    if include_trend:
        assert app.number_input(key="daily_intake").value == 1850.0


def test_failed_prediction_retains_previous_result_and_can_retry():
    app = build_app().run()
    app.button(key="analyze").click().run()
    app.number_input(key="Weight").set_value(80.0).run()
    with patch("sklearn.pipeline.Pipeline.predict", side_effect=RuntimeError("test failure")):
        app.button(key="analyze").click().run()
    assert not app.exception
    assert any("本次分析失败" in item.value for item in app.error)
    assert app.session_state["last_analysis"]["clean"]["Weight"] == 70.0
    app.button(key="analyze").click().run()
    assert app.session_state["last_analysis"]["clean"]["Weight"] == 80.0


def test_cleared_numeric_field_shows_missing_error_instead_of_crashing():
    app = build_app().run()
    app.number_input(key="Height").set_value(None).run()
    assert not app.exception
    assert any(item.value == "未填写" for item in app.metric)
    app.button(key="analyze").click().run()
    assert not app.exception
    assert any("身高" in item.value and "不能为空" in item.value for item in app.error)
