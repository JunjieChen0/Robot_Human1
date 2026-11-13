"""训练集拟合的七分类验证实验；置换时固定模型，不使用测试集。"""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import (
    FEATURE_NAMES, FIELD_DESCRIPTIONS_ZH, IMPUTED_NUMERIC_FEATURES,
    LABEL_COLUMN, MODELS_DIR, PROCESSED_DIR, RANDOM_STATE, REPORTS_DIR,
)


OUTPUT = REPORTS_DIR / "model_judgment"
FEATURES = {
    "Weight": ("体重", "千克（kg）", "问卷记录的体重；本实验不把体重解释为患病原因。"),
    "Height": ("身高", "米（m）", "问卷记录的身高，例如 1.70 表示 1.70 米。"),
    "Age": ("年龄", "岁", "问卷年龄；合成记录可能包含小数。"),
    "FAF": ("运动频率", "评分 0–3", "问卷体育活动频率评分，越大越频繁；不是每周运动小时数，也没有近期时间窗。"),
    "CH2O": ("饮水量（自动填充）", "问卷评分 1–3", "界面不采集此项，验证时统一填入训练集中位数；不是升数，也不是用户真实饮水量。"),
}
REPEATS = 30


def permutation_scores(model, features, labels, columns, repeats=REPEATS, seed=RANDOM_STATE):
    """每次从原数据复制，只打乱一列；返回基线及所有重复的原始分数。"""
    from sklearn.metrics import balanced_accuracy_score

    baseline = float(balanced_accuracy_score(labels, model.predict(features)))
    rng = np.random.default_rng(seed)
    rows = []
    for column in columns:
        for repeat in range(repeats):
            shuffled = features.copy()
            shuffled[column] = rng.permutation(features[column].to_numpy())
            score = float(balanced_accuracy_score(labels, model.predict(shuffled)))
            rows.append({"feature": column, "repeat": repeat + 1,
                         "baseline_score": baseline, "shuffled_score": score,
                         "score_drop": baseline - score})
    return baseline, pd.DataFrame(rows)


def summarize_importance(repeated):
    rows = []
    for feature, group in repeated.groupby("feature", sort=False):
        values = group["score_drop"].to_numpy()
        mean, std = float(values.mean()), float(values.std(ddof=0))
        rows.append({"feature": feature, "label": FEATURES[feature][0],
                     "mean_drop": mean, "std_drop": std,
                     "low": mean - std, "high": mean + std,
                     "repeats": len(values)})
    return pd.DataFrame(rows).sort_values("mean_drop", ascending=False).reset_index(drop=True)


def distribution_table(records, feature):
    """分布与案例使用同一批、同一输入口径的验证记录，含零样本档位。"""
    values = records[feature]
    if feature == "Age":
        buckets = pd.cut(values, [-np.inf, 18, 25, 35, 45, 65, np.inf], right=False,
                         labels=["小于18", "18至小于25", "25至小于35", "35至小于45", "45至小于65", "65及以上"])
        counts = buckets.value_counts(sort=False)
    elif feature in ("FAF", "CH2O"):
        buckets = pd.cut(values, [-np.inf, 0, 1, 2, 3],
                         labels=["0", "大于0至1", "大于1至2", "大于2至3"])
        counts = buckets.value_counts(sort=False)
    else:
        counts_array, edges = np.histogram(values, bins=10)
        names = [f"[{left:.2f}, {right:.2f}{']' if i == 9 else ')'}"
                 for i, (left, right) in enumerate(zip(edges[:-1], edges[1:]))]
        counts = pd.Series(counts_array, index=names)
    return pd.DataFrame({"区间": counts.index.astype(str), "样本量": counts.to_numpy(),
                         "占比": counts.to_numpy() / len(records)})


def input_dictionary():
    codes = {"Age": "岁", "Height": "米", "Weight": "kg", "FCVC": "评分1–3",
             "NCP": "主餐次数1–4", "CH2O": "问卷评分1–3；自动填充",
             "FAF": "评分0–3", "TUE": "问卷值0–2；自动填充", "Gender": "女性=0，男性=1",
             "CAEC": "从不=0，有时=1，经常=2，总是=3", "CALC": "从不=0，有时=1，经常=2，总是=3"}
    rows = []
    for name in FEATURE_NAMES:
        dummy = name.startswith("MTRANS_")
        rows.append({"输入列": name, "含义": FIELD_DESCRIPTIONS_ZH.get(name, "出行方式：" + name.removeprefix("MTRANS_")),
                     "单位或编码": "该方式=1，否则=0；汽车为四列全0" if dummy else codes.get(name, "否=0，是=1"),
                     "当前来源": "训练集中位数" if name in IMPUTED_NUMERIC_FEATURES else "问卷 / 表单"})
    return pd.DataFrame(rows)


def save_figure(importance, baseline, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for font in (Path("C:/Windows/Fonts/msyh.ttc"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")):
        if font.exists():
            font_manager.fontManager.addfont(str(font))
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(10, 4.8))
    y = np.arange(len(importance))
    ax.barh(y, importance.mean_drop * 100, color="#174ea6", height=.55)
    ax.errorbar(importance.mean_drop * 100, y, xerr=importance.std_drop * 100,
                fmt="o", color="#a63e00", capsize=4, label="均值 ±1标准差（30次置换）")
    ax.axvline(0, color="#465366", linewidth=1)
    ax.set_yticks(y, importance.label)
    ax.invert_yaxis()
    ax.set_xlim(left=min(-.5, float(importance.low.min()) * 100 - .5))
    ax.set_xlabel("平衡准确率平均下降（百分点；保留零值和负值）")
    ax.set_title(f"五项输入被打乱后，验证集表现平均下降多少？\n未打乱基线 {baseline:.2%}；仅训练集拟合的实验模型")
    ax.legend(loc="lower right")
    fig.text(.02, .015, "反映本实验模型对整批验证记录的依赖；不是个人患病原因。横线不是置信区间。", fontsize=10)
    fig.tight_layout(rect=(0, .045, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def generate():
    import joblib
    from src.train import build_models

    path = PROCESSED_DIR / "features.csv"
    if not path.is_file():
        raise FileNotFoundError("请先运行 python -m src.download_data 和 python -m src.preprocess。")
    data = pd.read_csv(path)
    if set(data["split"]) != {"train", "validation", "test"}:
        raise ValueError("需要预先固定的训练、验证、测试划分。")
    if data.groupby(FEATURE_NAMES, dropna=False)["split"].nunique().max() > 1:
        raise ValueError("相同输入跨划分，不能继续验证实验。")
    train = data.loc[data.split.eq("train")]
    validation = data.loc[data.split.eq("validation")]
    model = build_models()["RandomForest"]
    model.fit(train[FEATURE_NAMES], train[LABEL_COLUMN])
    features = validation[FEATURE_NAMES].copy()
    medians = {name: float(train[name].median()) for name in IMPUTED_NUMERIC_FEATURES}
    for name, value in medians.items():
        features[name] = value
    baseline, repeated = permutation_scores(model, features, validation[LABEL_COLUMN], FEATURES)
    importance = summarize_importance(repeated)
    records = features.copy()
    records.insert(0, "source_csv_row", validation.index + 2)
    records["true_label"] = validation[LABEL_COLUMN]
    records["predicted_label"] = model.predict(features)
    records["top_probability"] = model.predict_proba(features).max(axis=1)
    records["correct"] = records.true_label.eq(records.predicted_label)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(exist_ok=True)
    model_path = MODELS_DIR / "judgment_model.joblib"
    joblib.dump(model, model_path)
    importance.to_csv(OUTPUT / "feature_importance.csv", index=False)
    repeated.to_csv(OUTPUT / "permutation_repeats.csv", index=False)
    records.to_csv(OUTPUT / "validation_records.csv", index=False)
    input_dictionary().to_csv(OUTPUT / "input_dictionary.csv", index=False)
    summary = {
        "model": "RandomForest", "trees": 300, "fit_split": "train",
        "train_samples": len(train), "validation_samples": len(validation), "test_samples_used": 0,
        "input_policy": "prototype_median_imputation", "imputed_values": medians,
        "metric": "balanced_accuracy", "baseline_score": baseline,
        "features": list(FEATURES), "repeats": REPEATS, "seed": RANDOM_STATE,
        "correct_count": int(records.correct.sum()), "error_count": int((~records.correct).sum()),
        "std_definition": "population standard deviation across permutations (ddof=0), not a confidence interval",
        "processed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "versions": {name: version(name) for name in ("scikit-learn", "pandas", "numpy")},
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    save_figure(importance, baseline, OUTPUT / "feature_importance.png")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(importance.to_string(index=False))


if __name__ == "__main__":
    generate()
