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
    "FCVC": "蔬菜摄入量（1–3 分）",
    "NCP": "每日主餐次数",
    "CH2O": "每日饮水量（升）",
    "FAF": "每周运动频率（0–3）",
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

# 原型表单不采集的数值字段：模型训练时包含这两项，预测时用训练集中位数填充，
# 以保证输入仍为完整的 19 维特征，同时简化用户录入。
IMPUTED_NUMERIC_FEATURES = ("CH2O", "TUE")

# 原型表单实际采集的数值字段
FORM_NUMERIC_FEATURES = tuple(
    column for column in NUMERIC_FEATURES if column not in IMPUTED_NUMERIC_FEATURES
)

# 表单字段的详细说明（原型中的问号提示）
FIELD_HELP_ZH = {
    "FCVC": (
        "数据集的蔬菜摄入评分，取值 1–3："
        "1 = 很少吃蔬菜，2 = 适量，3 = 每餐都吃较多蔬菜。"
        "介于两档之间可填 0.5 的中间值（如 1.5、2.5）。"
    ),
    "FAVC": (
        "高热量食物指油炸食品、甜点、含糖饮料、肥肉等。"
        "选「是」表示多数日子都会摄入这类食物；选「否」表示偶尔或不常吃。"
    ),
    "FAF": (
        "数据集字段 FAF，官方释义为「你多久进行一次体育活动」，取值 0–3，"
        "数值越大表示运动越频繁。活动水平由该值映射：0 = 久坐，1–2 = 轻度活动，"
        "3 = 中度活动；当前录入范围内达不到「高度活动」。"
    ),
}

RANDOM_STATE = 42
