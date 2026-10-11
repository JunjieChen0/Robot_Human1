"""性别公平性二分类实验：train 只选验证集方案，evaluate 冻结后评价测试集。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fairlearn.metrics import MetricFrame, demographic_parity_difference, equalized_odds_difference
from fairlearn.reductions import EqualizedOdds, ExponentiatedGradient
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler

from src.config import FEATURE_NAMES, LABEL_COLUMN, PROCESSED_DIR, ROOT_DIR


OUTPUT = ROOT_DIR / "reports" / "fairness"
MODEL_PATH = ROOT_DIR / "models" / "fairness_bundle.joblib"
SEED = 42
BOUNDS = (0.01, 0.02, 0.05, 0.10, 0.20)
PERFORMANCE_TOLERANCE = 0.02
POSITIVE_LABELS = ("Obesity_Type_I", "Obesity_Type_II", "Obesity_Type_III")
GROUPS = ("女性", "男性")


def binary_labels(frame: pd.DataFrame) -> np.ndarray:
    return frame[LABEL_COLUMN].isin(POSITIVE_LABELS).astype(int).to_numpy()


def sensitive_groups(frame: pd.DataFrame) -> np.ndarray:
    if not frame["Gender"].isin([0, 1]).all():
        raise ValueError("性别字段必须是数据集的 Female=0 或 Male=1 编码。")
    return frame["Gender"].map({0: "女性", 1: "男性"}).to_numpy()


def counts(y_true, y_pred) -> tuple[int, int, int, int]:
    y, pred = np.asarray(y_true), np.asarray(y_pred)
    return (int(((y == 1) & (pred == 1)).sum()), int(((y == 1) & (pred == 0)).sum()),
            int(((y == 0) & (pred == 1)).sum()), int(((y == 0) & (pred == 0)).sum()))


def tpr(y_true, y_pred):
    tp, fn, _, _ = counts(y_true, y_pred)
    return tp / (tp + fn) if tp + fn else float("nan")


def fpr(y_true, y_pred):
    _, _, fp, tn = counts(y_true, y_pred)
    return fp / (fp + tn) if fp + tn else float("nan")


def balanced_accuracy(y_true, y_pred):
    return (tpr(y_true, y_pred) + 1 - fpr(y_true, y_pred)) / 2


def metrics() -> dict:
    return {
        "n": lambda y, p: len(y),
        "positive": lambda y, p: int(np.sum(y)),
        "negative": lambda y, p: int(len(y) - np.sum(y)),
        "label_rate": lambda y, p: float(np.mean(y)),
        "accuracy": accuracy_score,
        "balanced_accuracy": balanced_accuracy,
        "f1": lambda y, p: f1_score(y, p, zero_division=0) if np.sum(y) else float("nan"),
        "tpr": tpr,
        "fnr": lambda y, p: 1 - tpr(y, p),
        "fpr": fpr,
        "selection_rate": lambda y, p: float(np.mean(p)),
        "tp": lambda y, p: counts(y, p)[0],
        "fn": lambda y, p: counts(y, p)[1],
        "fp": lambda y, p: counts(y, p)[2],
        "tn": lambda y, p: counts(y, p)[3],
    }


def wilson_interval(successes, total):
    if not total or pd.isna(total):
        return float("nan"), float("nan")
    rate, z = successes / total, 1.959963984540054
    divisor = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / divisor
    radius = z * np.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / divisor
    return max(0.0, center - radius), min(1.0, center + radius)


def audit(y, pred, group) -> tuple[pd.DataFrame, dict]:
    """缺少正/负样本时保留 NaN；不以 0 冒充无法估计的错误率。"""
    mf = MetricFrame(metrics=metrics(), y_true=y, y_pred=pred, sensitive_features=group)
    by_group = mf.by_group.reindex(GROUPS).rename_axis("group").reset_index()
    overall = mf.overall.to_dict()
    rows = pd.concat([pd.DataFrame([{"group": "整体", **overall}]), by_group], ignore_index=True)
    rows["reliability"] = rows.apply(
        lambda r: "缺少正类或负类，部分指标不可估计" if pd.isna(r["n"]) or min(r["positive"], r["negative"]) == 0
        else "分母少于30，指标不稳定" if min(r["positive"], r["negative"]) < 30
        else "可计算；仍需结合区间与代表性解释", axis=1,
    )
    for rate, numerator, denominator in (("tpr", "tp", "positive"), ("fpr", "fp", "negative")):
        intervals = [wilson_interval(r[numerator], r[denominator]) for _, r in rows.iterrows()]
        rows[rate + "_low"], rows[rate + "_high"] = zip(*intervals)
    complete = by_group[["positive", "negative"]].gt(0).all().all()
    overall["equalized_odds_difference"] = float(equalized_odds_difference(y, pred, sensitive_features=group)) if complete else float("nan")
    overall["demographic_parity_difference"] = float(demographic_parity_difference(y, pred, sensitive_features=group)) if by_group["n"].gt(0).all() else float("nan")
    differences = mf.difference()
    for key in ("tpr", "fpr", "balanced_accuracy", "f1"):
        overall[key + "_difference"] = float(differences[key]) if complete else float("nan")
    return rows, overall


def choose_candidate(comparison: pd.DataFrame) -> str:
    baseline = comparison.loc[comparison["model"].eq("baseline")].iloc[0]
    candidates = comparison.loc[comparison["model"].ne("baseline")].copy()
    eligible = candidates.loc[
        candidates["balanced_accuracy"].ge(baseline["balanced_accuracy"] - PERFORMANCE_TOLERANCE)
        & candidates["f1"].ge(baseline["f1"] - PERFORMANCE_TOLERANCE)
    ]
    if len(eligible):
        return str(eligible.sort_values(["equalized_odds_difference", "balanced_accuracy", "bound"], ascending=[True, False, True]).iloc[0]["model"])
    # 不满足性能底线时仍报告最接近底线的尝试，但不将其推荐为替代方案。
    candidates["loss"] = np.maximum(baseline["balanced_accuracy"] - candidates["balanced_accuracy"], baseline["f1"] - candidates["f1"])
    return str(candidates.sort_values(["loss", "equalized_odds_difference", "bound"]).iloc[0]["model"])


def read_data() -> pd.DataFrame:
    data = pd.read_csv(PROCESSED_DIR / "features.csv")
    if set(data["split"]) != {"train", "validation", "test"}:
        raise ValueError("需要预先划分的训练、验证和测试集。")
    # 同特征跨集合时拒绝继续，避免重复样本泄漏。
    if data.groupby(FEATURE_NAMES, dropna=False)["split"].nunique().max() != 1:
        raise ValueError("发现相同特征记录跨划分。")
    return data


def write_json(path: Path, value):
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, (tuple, list)):
            return [clean(v) for v in obj]
        if isinstance(obj, (np.floating, float)):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.integer):
            return int(obj)
        return obj
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def train() -> None:
    data = read_data()
    train_frame = data.loc[data["split"].eq("train")]
    validation = data.loc[data["split"].eq("validation")]
    scaler = StandardScaler().fit(train_frame[FEATURE_NAMES])
    x_train, x_val = scaler.transform(train_frame[FEATURE_NAMES]), scaler.transform(validation[FEATURE_NAMES])
    y_train, y_val = binary_labels(train_frame), binary_labels(validation)
    a_train, a_val = sensitive_groups(train_frame), sensitive_groups(validation)
    estimator = LogisticRegression(C=1.0, max_iter=3000, random_state=SEED)
    baseline = estimator.fit(x_train, y_train)
    _, base_metrics = audit(y_val, baseline.predict(x_val), a_val)
    comparison = [{"model": "baseline", "bound": np.nan, **base_metrics}]
    models = {}
    for bound in BOUNDS:
        name = f"eo_{bound:.2f}"
        model = ExponentiatedGradient(
            LogisticRegression(C=1.0, max_iter=3000, random_state=SEED),
            EqualizedOdds(difference_bound=bound), eps=0.01, max_iter=50,
        )
        model.fit(x_train, y_train, sensitive_features=a_train)
        _, result = audit(y_val, model.predict(x_val, random_state=SEED), a_val)
        comparison.append({"model": name, "bound": bound, **result})
        models[name] = model
        print(f"验证集 {name}: balanced_accuracy={result['balanced_accuracy']:.4f}, F1={result['f1']:.4f}, EO差值={result['equalized_odds_difference']:.4f}", flush=True)
    comparison = pd.DataFrame(comparison)
    selected = choose_candidate(comparison)
    chosen = comparison.loc[comparison["model"].eq(selected)].iloc[0]
    within_tolerance = bool(chosen["balanced_accuracy"] >= base_metrics["balanced_accuracy"] - PERFORMANCE_TOLERANCE and chosen["f1"] >= base_metrics["f1"] - PERFORMANCE_TOLERANCE)
    metadata = {
        "selected": selected, "constraint_bound": float(chosen["bound"]), "random_seed": SEED,
        "bounds": BOUNDS, "positive_labels": POSITIVE_LABELS, "sensitive_attribute": "Gender",
        "selection_rule": "验证集平衡准确率与F1下降均不超过0.02，优先EO差值最小；无合格项时报告最大性能损失最小的尝试，不推荐替换。并列按平衡准确率、约束上限排序。",
        "within_validation_tolerance": within_tolerance,
        "training_samples": len(train_frame), "validation_samples": len(validation),
        "fit_includes_validation": False, "preprocessing_fit_split": "train",
        "feature_names": FEATURE_NAMES,
        "processed_sha256": hashlib.sha256((PROCESSED_DIR / "features.csv").read_bytes()).hexdigest(),
        "prediction_policy": "基线默认0.5判定；EG调用predict(random_state=42)，保持随机混合策略，不将混合概率另行阈值化。",
        "predeclared_selection": {"balanced_accuracy_drop_limit": PERFORMANCE_TOLERANCE, "f1_drop_limit": PERFORMANCE_TOLERANCE},
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.parent.mkdir(exist_ok=True)
    comparison.to_csv(OUTPUT / "validation_comparison.csv", index=False)
    write_json(OUTPUT / "selection.json", metadata)
    joblib.dump({"scaler": scaler, "baseline": baseline, "mitigated": models[selected], "metadata": metadata}, MODEL_PATH)
    print(f"已锁定方案 {selected}；测试集尚未评价。", flush=True)


def bootstrap_delta(y, baseline, mitigated, groups, repeats=1000):
    """同组内成对重采样，保持两模型对比配对；不重新训练模型。"""
    rng = np.random.default_rng(SEED)
    indices = [np.flatnonzero(groups == g) for g in GROUPS]
    def fast(y, p, a):
        tp, fn, fp, tn = counts(y, p)
        rates = [(tpr(y[a == g], p[a == g]), fpr(y[a == g], p[a == g])) for g in GROUPS]
        return np.array([balanced_accuracy(y, p), 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else np.nan,
                         max(np.ptp([r[0] for r in rates]), np.ptp([r[1] for r in rates]))])
    samples = []
    for _ in range(repeats):
        idx = np.concatenate([rng.choice(i, size=len(i), replace=True) for i in indices])
        samples.append(fast(y[idx], mitigated[idx], groups[idx]) - fast(y[idx], baseline[idx], groups[idx]))
    draws = np.asarray(samples)
    result = {}
    for i, key in enumerate(("balanced_accuracy", "f1", "equalized_odds_difference")):
        valid = draws[:, i][np.isfinite(draws[:, i])]
        result[key] = {"low": float(np.quantile(valid, .025)), "high": float(np.quantile(valid, .975)), "valid_repeats": len(valid)} if len(valid) else {"low": None, "high": None, "valid_repeats": 0}
    return result


def evaluate() -> None:
    bundle = joblib.load(MODEL_PATH)
    expected = bundle["metadata"]["processed_sha256"]
    if hashlib.sha256((PROCESSED_DIR / "features.csv").read_bytes()).hexdigest() != expected:
        raise ValueError("数据已变化；请重新训练并重新锁定验证集方案。")
    data = read_data()
    stats = []
    for split, frame in [("all", data), *data.groupby("split", sort=False)]:
        for g in GROUPS:
            subset = frame.loc[sensitive_groups(frame) == g]
            y = binary_labels(subset)
            stats.append({"split": split, "group": g, "n": len(y), "positive": int(y.sum()), "negative": int(len(y) - y.sum()), "label_rate": float(y.mean()) if len(y) else np.nan})
    pd.DataFrame(stats).to_csv(OUTPUT / "group_counts.csv", index=False)
    test = data.loc[data["split"].eq("test")]
    x, y, groups = bundle["scaler"].transform(test[FEATURE_NAMES]), binary_labels(test), sensitive_groups(test)
    predictions = {"baseline": bundle["baseline"].predict(x), "mitigated": bundle["mitigated"].predict(x, random_state=SEED)}
    comparisons, group_tables = [], []
    for name, pred in predictions.items():
        rows, result = audit(y, pred, groups)
        comparisons.append({"model": name, **result})
        rows.insert(0, "model", name)
        group_tables.append(rows)
    pd.concat(group_tables, ignore_index=True).to_csv(OUTPUT / "test_group_metrics.csv", index=False)
    pd.DataFrame(comparisons).to_csv(OUTPUT / "test_comparison.csv", index=False)
    pd.DataFrame({"row_id": test.index, "group": groups, "y_true": y, **predictions}).to_csv(OUTPUT / "test_predictions.csv", index=False)
    # 固定的多随机种子诊断只说明随机混合的波动，不参与模型/种子选择。
    seed_rows = []
    for seed in range(100):
        _, result = audit(y, bundle["mitigated"].predict(x, random_state=seed), groups)
        seed_rows.append({"seed": seed, **result})
    pd.DataFrame(seed_rows).to_csv(OUTPUT / "randomization_sensitivity.csv", index=False)
    write_json(OUTPUT / "test_summary.json", {
        "selection": bundle["metadata"], "test_samples": len(test), "test_metrics": comparisons,
        "bootstrap_delta_mitigated_minus_baseline": bootstrap_delta(y, predictions["baseline"], predictions["mitigated"], groups),
        "bootstrap_note": "固定训练模型和seed=42测试预测，按性别组内成对重采样1000次，百分位95%区间。未覆盖重训波动、合成样本相关性、标签偏差与新用户外推。",
        "model_sha256": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
    })
    print(pd.DataFrame(comparisons)[["model", "accuracy", "balanced_accuracy", "f1", "equalized_odds_difference", "demographic_parity_difference"]].to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("train", "evaluate"))
    args = parser.parse_args()
    {"train": train, "evaluate": evaluate}[args.stage]()


if __name__ == "__main__":
    main()
