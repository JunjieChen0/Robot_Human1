from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.model_judgment import FEATURES


APP = Path(__file__).resolve().parents[1] / "app.py"


def open_judgment():
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    return app.radio(key="main_page").set_value("模型判断").run()


def test_standalone_entry_opens_judgment_without_loading_health_model():
    app = AppTest.from_file(str(APP.parent / "model_judgment_app.py"), default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value == "模型判断"
    assert app.selectbox(key="judgment_feature").value in FEATURES


def test_judgment_feature_selection_links_distribution_and_both_cases():
    app = open_judgment()
    assert not app.exception
    assert app.title[0].value == "模型判断"
    for feature, (label, _, _) in FEATURES.items():
        app.selectbox(key="judgment_feature").set_value(feature).run()
        assert not app.exception
        assert f"输入证据：{label}" in [item.value for item in app.subheader]
        distribution = next(item.value for item in app.dataframe if "区间" in item.value)
        assert distribution["样本量"].sum() == 421
        cases = [item.value for item in app.dataframe if "定位" in item.value]
        assert len(cases) == 2
        for table in cases:
            assert table.loc[table["定位"].eq("当前选中特征"), "输入列"].tolist() == [feature]
    assert any("打乱常量不会改变" in item.value for item in app.info)
    assert any("不能解释单条记录" in item.value for item in app.warning)


def test_judgment_first_response_requires_answers_and_locks_original():
    app = open_judgment()
    save = next(button for button in app.button if button.label == "保存首次回答")
    save.click().run()
    assert any("填写匿名编号" in item.value for item in app.error)
    app.text_input(key="judgment_participant").set_value("自动测试，不是真人记录")
    app.text_input(key="judgment_ranking").set_value("体重，平均下降最多")
    app.text_area(key="judgment_causality").set_value("不能；不是个人病因或局部解释")
    next(button for button in app.button if button.label == "保存首次回答").click().run()
    assert not app.exception
    original = dict(app.session_state["judgment_response"])
    assert original["task_1"] == "体重，平均下降最多"
    assert original["experiment_model_sha256"]
    app.text_input(key="judgment_ranking").set_value("后续改写")
    next(button for button in app.button if button.label == "保存首次回答").click().run()
    assert dict(app.session_state["judgment_response"]) == original
    assert next(button for button in app.button if button.label == "保存首次回答").disabled


def test_health_snapshot_and_draft_survive_judgment_navigation():
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    app.button(key="analyze").click().run()
    snapshot = app.session_state["last_analysis"]["time"]
    app.number_input(key="Weight").set_value(82.).run()
    app.radio(key="main_page").set_value("模型判断").run()
    app.radio(key="main_page").set_value("体重管理原型").run()
    assert not app.exception
    assert app.number_input(key="Weight").value == 82.
    assert app.session_state["last_analysis"]["time"] == snapshot
    assert any("输入已修改" in item.value for item in app.warning)
