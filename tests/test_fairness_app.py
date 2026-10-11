"""审核页面的导航、筛选和理解自测。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_fairness_page_filters_and_explains_results():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    app.radio(key="main_page").set_value("模型公平性审核").run()
    assert not app.exception
    assert "模型公平性审核" in [x.value for x in app.title]
    app.selectbox(key="fairness_group").set_value("男性").run()
    app.selectbox(key="fairness_metric").set_value("漏判率 FNR").run()
    assert not app.exception
    assert set(app.dataframe[0].value["群体"]) == {"男性"}
    app.radio(key="fairness_quiz").set_value("不能，还要比较各组错误率和样本量").run()
    app.button(key="fairness_quiz_check").click().run()
    assert any("理解正确" in x.value for x in app.success)
    app.radio(key="main_page").set_value("体重管理原型").run()
    assert not app.exception
    assert any("估计并分析趋势" in b.label for b in app.button)
