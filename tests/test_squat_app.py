from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def test_standalone_squat_entry_does_not_need_health_models():
    app = AppTest.from_file(str(ROOT / "squat_counter_app.py"), default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value == "深蹲计数"


def test_squat_page_preserves_existing_health_draft_and_snapshot():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    app.button(key="analyze").click().run()
    snapshot = app.session_state["last_analysis"]["time"]
    app.number_input(key="Weight").set_value(81.).run()
    app.radio(key="main_page").set_value("深蹲计数").run()
    assert not app.exception
    assert app.title[0].value == "深蹲计数"
    app.radio(key="main_page").set_value("体重管理原型").run()
    assert app.number_input(key="Weight").value == 81.
    assert app.session_state["last_analysis"]["time"] == snapshot
