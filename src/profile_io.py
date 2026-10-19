"""单人问卷 CSV 导入；沿用界面相同的校验和中位数填充口径。"""

import csv
from io import StringIO

import pandas as pd

from src.config import FIELD_DESCRIPTIONS_ZH, FORM_FIELDS, IMPUTED_NUMERIC_FEATURES
from src.validation import validate_profile


def parse_profile_csv(content: bytes, ranges: dict) -> tuple[dict, list[str], list[str]]:
    """仅接收 UTF-8 的一行档案，失败时不返回可载入的部分数据。"""

    if len(content) > 1024 * 1024:
        return {}, ["文件超过 1 MB，请使用仅含一人档案的 CSV 模板。"], []
    try:
        text = content.decode("utf-8-sig")
        headers = next(csv.reader(StringIO(text)), [])
        if len(headers) != len(set(headers)):
            return {}, ["列名重复，请使用模板中唯一的英文列名。"], []
        frame = pd.read_csv(StringIO(text))
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError, csv.Error):
        return {}, ["无法读取文件。请另存为 CSV UTF-8（逗号分隔），保留模板表头。"], []
    if len(frame) != 1:
        return {}, ["每次仅支持 1 行个人档案，请保留表头和一行数据。"], []
    missing = [name for name in FORM_FIELDS if name not in frame.columns]
    if missing:
        return {}, [f"缺少列 {name}（{FIELD_DESCRIPTIONS_ZH[name]}），请按模板补齐。" for name in missing], []
    row = frame.iloc[0]
    blank = [name for name in FORM_FIELDS if pd.isna(row[name]) or str(row[name]).strip() == ""]
    if blank:
        return {}, [f"{FIELD_DESCRIPTIONS_ZH[name]} 不能为空，请填写后重新导入。" for name in blank], []
    profile = {name: row[name] for name in FORM_FIELDS}
    for name in IMPUTED_NUMERIC_FEATURES:
        profile[name] = float(ranges[name]["median"])
    clean, errors = validate_profile(profile)
    extra = [name for name in frame.columns if name not in FORM_FIELDS]
    notices = ["以下额外列不参与导入：" + "、".join(extra)] if extra else []
    return ({} if errors else {name: clean[name] for name in FORM_FIELDS}), errors, notices
