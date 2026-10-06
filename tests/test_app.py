"""原型端到端冒烟测试：用 Streamlit AppTest 无头运行 app.py。

这类测试能捕获"只在提交表单后才暴露"的错误——例如函数返回值未接收导致的
NameError（迭代 7 曾出现：render_weight_log_inputs() 的返回值漏接）。
仅做冒烟检查，不校验具体预测数值。
"""

from __future__ import annotations

from pathlib import Path

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


def test_load_demo_profile_runs_without_exception():
    app = build_app()
    app.run()
    find_button(app, "载入").click().run()
    assert not app.exception
