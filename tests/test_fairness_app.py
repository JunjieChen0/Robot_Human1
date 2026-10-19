"""审核页面的导航、筛选和理解自测。"""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df


def test_fairness_page_filters_and_explains_results():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    app.radio(key="main_page").set_value("模型公平性审核").run()
    assert not app.exception
    assert "模型公平性审核" in [x.value for x in app.title]
    app.selectbox(key="fairness_group").set_value("男性").run()
    app.selectbox(key="fairness_metric").set_value("漏判率 FNR").run()
    assert not app.exception
    assert set(app.dataframe[0].value["群体"]) == {"男性"}
    assert len(app.dataframe[0].value.columns) == 7
    assert set(app.dataframe[0].value["漏判数"]) == {2}
    assert set(app.dataframe[0].value["误判数"]) == {1}
    assert any("正类数" in item.value.columns and "F1" in item.value.columns for item in app.dataframe)
    chart = json.loads(app.get("vega_lite_chart")[0].proto.spec)
    assert chart["encoding"]["x"]["axis"]["format"] == ".2%"
    assert chart["encoding"]["y"]["axis"]["labelAngle"] == 0
    assert next(item.value for item in app.metric if item.label == "错误率群体差值 EO") == "2.08 个百分点"
    intervals = next(item for item in app.dataframe if "识别率 TPR 下限" in item.value.columns)
    shown = convert_arrow_bytes_to_pandas_df(intervals.proto.arrow_data.styler.display_values)
    assert set(shown["误判率 FPR 下限"]) == {"0.15%"}
    assert all(value.endswith("%") for value in shown["识别率 TPR 下限"])
    app.radio(key="fairness_quiz").set_value("不能，还要比较各组错误率和样本量").run()
    app.button(key="fairness_quiz_check").click().run()
    assert any("理解正确" in x.value for x in app.success)
    app.radio(key="main_page").set_value("体重管理原型").run()
    assert not app.exception
    assert any("估计并分析趋势" in b.label for b in app.button)
