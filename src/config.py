"""项目路径、标签和特征配置。"""

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_CSV = RAW_DIR / "uci544" / "ObesityDataSet_raw_and_data_sinthetic.csv"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "sample"
MODELS_DIR = ROOT_DIR / "models"
REPORTS_DIR = ROOT_DIR / "reports"
REPORT_TABLES_DIR = REPORTS_DIR / "tables"
REPORT_FIGURES_DIR = REPORTS_DIR / "figures"

DATA_URL = (
    "https://archive.ics.uci.edu/static/public/544/"
    "estimation+of+obesity+levels+based+on+eating+habits+and+physical+condition.zip"
)

LABEL_COLUMN = "NObeyesdad"

LABEL_NAMES_ZH = {
    "Insufficient_Weight": "体重偏低",
    "Normal_Weight": "正常体重",
    "Overweight_Level_I": "超重 I 级",
    "Overweight_Level_II": "超重 II 级",
    "Obesity_Type_I": "肥胖 I 型",
    "Obesity_Type_II": "肥胖 II 型",
    "Obesity_Type_III": "肥胖 III 型",
}
LABEL_ORDER = list(LABEL_NAMES_ZH)

NUMERIC_FEATURES = (
    "Age",
    "Height",
    "Weight",
    "FCVC",
    "NCP",
    "CH2O",
    "FAF",
    "TUE",
)

BINARY_FEATURES = (
    "Gender",
    "family_history_with_overweight",
    "FAVC",
    "SMOKE",
    "SCC",
)

ORDINAL_FEATURES = ("CAEC", "CALC")
ORDINAL_LEVELS = {"no": 0, "Sometimes": 1, "Frequently": 2, "Always": 3}

NOMINAL_FEATURE = "MTRANS"
NOMINAL_BASELINE = "Automobile"
NOMINAL_DUMMIES = ("Bike", "Motorbike", "Public_Transportation", "Walking")

FEATURE_NAMES = (
    list(NUMERIC_FEATURES)
    + list(BINARY_FEATURES)
    + list(ORDINAL_FEATURES)
    + [f"{NOMINAL_FEATURE}_{level}" for level in NOMINAL_DUMMIES]
)

FIELD_DESCRIPTIONS_ZH = {
    "Age": "年龄（岁）",
    "Height": "身高（米）",
    "Weight": "体重（千克）",
    "FCVC": "每餐蔬菜份数",
    "NCP": "每日主餐次数",
    "CH2O": "每日饮水量（升）",
    "FAF": "每周运动小时数",
    "TUE": "每日电子设备使用小时数",
    "Gender": "性别",
    "family_history_with_overweight": "家族超重史",
    "FAVC": "经常高热量饮食",
    "SMOKE": "吸烟",
    "SCC": "记录每日热量摄入",
    "CAEC": "两餐之间加餐频率",
    "CALC": "饮酒频率",
    "MTRANS": "主要出行方式",
}

RANDOM_STATE = 42
