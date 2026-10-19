import json

import pandas as pd
import pytest

from src.config import FORM_FIELDS, MODELS_DIR
from src.profile_io import parse_profile_csv
from tests.test_validation import valid_row


RANGES = json.loads((MODELS_DIR / "raw_ranges.json").read_text(encoding="utf-8"))


def csv_bytes(row=None):
    profile = {name: valid_row()[name] for name in FORM_FIELDS}
    profile.update(row or {})
    return pd.DataFrame([profile]).to_csv(index=False).encode("utf-8-sig")


def test_import_accepts_utf8_bom_and_returns_only_form_fields():
    profile, errors, _ = parse_profile_csv(csv_bytes(), RANGES)
    assert not errors
    assert set(profile) == set(FORM_FIELDS)
    assert profile["Height"] == 1.7


@pytest.mark.parametrize("changes,expected", [
    ({"Height": 170}, "身高"),
    ({"Weight": ""}, "不能为空"),
    ({"Gender": ""}, "不能为空"),
    ({"CAEC": "often"}, "CAEC"),
    ({"Weight": float("inf")}, "体重"),
], ids=["centimeters", "blank-weight", "blank-gender", "bad-category", "infinite-weight"])
def test_import_rejects_invalid_fields_without_partial_profile(changes, expected):
    profile, errors, _ = parse_profile_csv(csv_bytes(changes), RANGES)
    assert profile == {}
    assert any(expected in error for error in errors)


def test_import_reports_missing_columns_and_ignores_extra_columns_explicitly():
    profile, errors, notices = parse_profile_csv(csv_bytes({"CH2O": 999}), RANGES)
    assert not errors
    assert "CH2O" not in profile
    assert "CH2O" in notices[0]
    _, errors, _ = parse_profile_csv(b"Age,Height\n25,1.7\n", RANGES)
    assert any("Weight" in error for error in errors)


@pytest.mark.parametrize("content,expected", [
    (b"", "无法读取"),
    (b"\xff\xfe", "无法读取"),
    (b"Age,Age\n25,25\n", "列名重复"),
    (b"Age\n25\n26\n", "1 行"),
    (b"x" * (1024 * 1024 + 1), "1 MB"),
], ids=["empty", "non-utf8", "duplicate-header", "multiple-people", "too-large"])
def test_import_rejects_unusable_files(content, expected):
    profile, errors, _ = parse_profile_csv(content, RANGES)
    assert not profile
    assert expected in errors[0]
