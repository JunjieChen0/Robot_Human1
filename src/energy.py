"""能量平衡与体重趋势外推的纯函数模型。"""

from __future__ import annotations

KCAL_PER_KG = 7700.0

ACTIVITY_FACTORS = {
    "久坐": 1.2,
    "轻度活动": 1.375,
    "中度活动": 1.55,
    "高度活动": 1.725,
}


def bmr_mifflin_st_jeor(weight_kg: float, height_m: float, age_years: float, male: bool) -> float:
    """Mifflin-St Jeor 基础代谢估算，身高以米为单位传入。"""

    base = 10.0 * weight_kg + 6.25 * height_m * 100.0 - 5.0 * age_years
    return base + (5.0 if male else -161.0)


def activity_level_from_exercise(activity_score: float) -> str:
    """把运动频率等级（FAF，取值 0–3）映射到活动水平。

    档位阈值沿用 1/3/5 的刻度，而 FAF 上限为 3，因此「高度活动」在当前
    录入范围内不可达，界面据此披露活动水平的上限。
    """

    if activity_score < 1.0:
        return "久坐"
    if activity_score < 3.0:
        return "轻度活动"
    if activity_score < 5.0:
        return "中度活动"
    return "高度活动"


def tdee(weight_kg: float, height_m: float, age_years: float, male: bool, activity: str) -> float:
    return bmr_mifflin_st_jeor(weight_kg, height_m, age_years, male) * ACTIVITY_FACTORS[activity]


def project_weight(
    current_kg: float,
    daily_intake_kcal: float,
    daily_expenditure_kcal: float,
    days: int,
    step_days: int = 7,
) -> list[dict[str, float]]:
    """按每日能量差线性外推体重，7700 kcal 折合 1 kg。"""

    daily_deficit = daily_expenditure_kcal - daily_intake_kcal
    points = [{"day": 0.0, "weight_kg": round(current_kg, 2)}]
    projection_days = list(range(step_days, days + 1, step_days))
    if days > 0 and days % step_days:
        projection_days.append(days)
    for day in projection_days:
        projected = current_kg - daily_deficit * day / KCAL_PER_KG
        points.append({"day": float(day), "weight_kg": round(projected, 2)})
    return points
