"""从冻结的公平性实验产物生成中文图表与报告正文。"""

import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from fairlearn.reductions import EqualizedOdds

from src.config import FEATURE_NAMES
from src.fairness import GROUPS, MODEL_PATH, OUTPUT, SEED, audit, binary_labels, read_data, sensitive_groups, write_json


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |", *["| " + " | ".join(map(str, r)) + " |" for r in rows]])


def generate():
    for font in (Path("C:/Windows/Fonts/msyh.ttc"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")):
        if font.exists():
            font_manager.fontManager.addfont(str(font))
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
            break
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    counts = pd.read_csv(OUTPUT / "group_counts.csv")
    validation = pd.read_csv(OUTPUT / "validation_comparison.csv")
    overall = pd.read_csv(OUTPUT / "test_comparison.csv").set_index("model")
    groups = pd.read_csv(OUTPUT / "test_group_metrics.csv")
    summary = json.loads((OUTPUT / "test_summary.json").read_text(encoding="utf-8"))
    bundle = joblib.load(MODEL_PATH)
    data = read_data()
    train = data.loc[data.split.eq("train")]
    x_train = bundle["scaler"].transform(train[FEATURE_NAMES])
    y_train, a_train = binary_labels(train), sensitive_groups(train)
    constraint = EqualizedOdds(difference_bound=summary["selection"]["constraint_bound"])
    constraint.load_data(x_train, y_train, sensitive_features=a_train)
    gamma_max = float(constraint.gamma(bundle["baseline"].predict).max())
    train_rows = []
    for model_name in ("baseline", "mitigated"):
        model = bundle[model_name]
        pred = model.predict(x_train) if model_name == "baseline" else model.predict(x_train, random_state=SEED)
        _, scores = audit(y_train, pred, a_train)
        train_rows.append({"model": model_name, **scores})
    pd.DataFrame(train_rows).to_csv(OUTPUT / "training_diagnostics.csv", index=False)
    weights = {str(k): float(v) for k, v in bundle["mitigated"].weights_.items()}
    write_json(OUTPUT / "constraint_diagnostics.json", {"baseline_max_group_to_overall_deviation": gamma_max, "constraint_bound": summary["selection"]["constraint_bound"], "weights": weights, "best_gap": bundle["mitigated"].best_gap_, "oracle_calls": bundle["mitigated"].n_oracle_calls_})

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(OUTPUT / name, dpi=180, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 2.8))
    for ax, split, title in zip(axes, ["all", "test"], ["全部数据", "测试集"]):
        rows = counts.loc[counts.split.eq(split)].set_index("group").loc[list(GROUPS)]
        ax.bar(GROUPS, rows.negative, label="负类", color="#92adc4")
        ax.bar(GROUPS, rows.positive, bottom=rows.negative, label="正类", color="#376889")
        for i, row in enumerate(rows.itertuples()):
            ax.text(i, row.negative / 2, str(row.negative), ha="center")
            ax.text(i, row.negative + row.positive / 2, str(row.positive), ha="center", color="white")
        ax.set_title(title); ax.set_ylabel("记录数"); ax.legend(loc="upper right", fontsize=8)
    save(fig, "group_counts.png")

    fig, ax = plt.subplots(figsize=(9, 2.8))
    for key, label in [("balanced_accuracy", "平衡准确率"), ("f1", "F1"), ("equalized_odds_difference", "EO 差值")]:
        ax.plot(validation.loc[1:, "bound"], validation.loc[1:, key], marker="o", label=label)
    ax.set(xlabel="EqualizedOdds 训练约束上限", ylabel="验证集指标", ylim=(-.03, 1.08))
    ax.set_xscale("log"); ax.set_xticks(validation.loc[1:, "bound"], [f"{b:.2f}" for b in validation.loc[1:, "bound"]]); ax.legend(ncol=3, fontsize=9)
    save(fig, "validation_tradeoff.png")

    fig, axes = plt.subplots(1, 2, figsize=(9, 2.8))
    for i, (key, title) in enumerate([("balanced_accuracy", "测试集平衡准确率"), ("equalized_odds_difference", "测试集 EO 差值")]):
        values = overall.loc[["baseline", "mitigated"], key]
        axes[i].bar(["基线", "约束方案"], values, color=["#376889", "#c17c3a"])
        axes[i].set_ylim(0, 1.1 if i == 0 else .04)
        for j, v in enumerate(values): axes[i].text(j, v, f"{v:.4f}", ha="center", va="bottom")
        axes[i].set_title(title + (" ↑" if i == 0 else " ↓"))
    save(fig, "test_comparison.png")

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.1))
    for ax, metric, title in zip(axes, ["tpr", "fpr"], ["正类识别率 TPR", "负类误判率 FPR"]):
        for offset, model_name, label, color in [(-.12, "baseline", "基线", "#376889"), (.12, "mitigated", "约束方案", "#c17c3a")]:
            rows = groups.loc[groups.model.eq(model_name)].set_index("group").loc[list(GROUPS)]
            values = rows[metric].to_numpy()
            errors = np.vstack([np.maximum(values - rows[metric + "_low"], 0), np.maximum(rows[metric + "_high"] - values, 0)])
            ax.errorbar(np.arange(2) + offset, values, yerr=errors, fmt="o", capsize=4, label=label, color=color)
        ax.set_xticks([0, 1], GROUPS); ax.set_xlim(-.5, 1.5)
        ax.set_ylim(.90, 1.01) if metric == "tpr" else ax.set_ylim(-.005, .065)
        ax.set_title(title); ax.legend(fontsize=8)
    save(fig, "group_rates.png")

    names = {"baseline": "基线", "mitigated": "约束方案"}
    pct = lambda value: f"{value:.2%}"
    count_table = table(["划分与群体", "样本量", "正类", "负类", "正类比例"], [[{"all": "全部", "train": "训练", "validation": "验证", "test": "测试"}[r.split] + " / " + r.group, r.n, r.positive, r.negative, pct(r.label_rate)] for r in counts.itertuples()])
    val_table = table(["方案", "约束上限", "平衡准确率", "F1", "EO 差值"], [["基线" if r.model == "baseline" else r.model, "—" if pd.isna(r.bound) else f"{r.bound:.2f}", f"{r.balanced_accuracy:.4f}", f"{r.f1:.4f}", f"{r.equalized_odds_difference:.4f}"] for r in validation.itertuples()])
    metric_table = table(["指标", "基线", "约束方案", "变化"], [[label, f"{overall.loc['baseline', key]:.4f}", f"{overall.loc['mitigated', key]:.4f}", f"{overall.loc['mitigated', key]-overall.loc['baseline', key]:+.4f}"] for key, label in [("accuracy", "准确率"), ("balanced_accuracy", "平衡准确率"), ("f1", "正类 F1"), ("equalized_odds_difference", "EO 差值"), ("demographic_parity_difference", "DP 差值")]])
    subgroup = groups.loc[groups.group.ne("整体")]
    performance_table = table(["方案与群体", "平衡准确率", "F1", "漏判率 FNR", "预测正类比例"], [[names[r.model]+" / "+r.group, pct(r.balanced_accuracy), f"{r.f1:.4f}", pct(r.fnr), pct(r.selection_rate)] for r in subgroup.itertuples()])
    error_table = table(["方案与群体", "TPR", "FPR", "漏判 / 正类", "误判 / 负类"], [[names[r.model]+" / "+r.group, pct(r.tpr), pct(r.fpr), f"{int(r.fn)}/{int(r.positive)}", f"{int(r.fp)}/{int(r.negative)}"] for r in subgroup.itertuples()])
    predictions = pd.read_csv(OUTPUT / "test_predictions.csv")
    errors = predictions.loc[predictions.y_true.ne(predictions.baseline)].copy()
    error_examples = []
    for r in errors.itertuples():
        original = data.loc[r.row_id]
        error_examples.append([r.row_id + 1, r.group, "漏判" if r.y_true == 1 else "误判", original["NObeyesdad"], f"{original.Weight / original.Height ** 2:.2f}"])
    error_example_table = table(["数据行号", "群体", "错误", "原七分类标签", "BMI"], error_examples)
    baseline_female = subgroup.loc[subgroup.model.eq("baseline") & subgroup.group.eq("女性")].iloc[0]
    seed_rows = pd.read_csv(OUTPUT / "randomization_sensitivity.csv")
    report = f'''# 健康数据模型公平性分析报告

本实验在 WeightTrend 项目上增加性别公平性审核。基线与约束方案的测试集平衡准确率均为 {overall.loc['baseline','balanced_accuracy']:.2%}，EO 差值均为 {overall.loc['baseline','equalized_odds_difference']:.4f}。本次改进尝试没有改变测试预测，不能据此宣称已经改善公平性。

## 一 审核对象与分组

使用 UCI 544 的 2111 条记录。原七分类标签中，肥胖 I、II、III 型合并为正类；体重偏低、正常体重、超重 I、II 级合并为负类。负类不等于健康，正类也不是医疗诊断。目标是检查该标签判定在数据集记录为 Female 和 Male 的人群中是否存在错误率差异。

本次完成基础任务，只审核性别。分组直接采用原数据字段，不从姓名或外貌推断；数据没有其他性别身份编码，不能据此评价其表现。可能受影响的是依赖页面理解自身输入与模型标签关系的使用者；漏判可能带来错误的安心，误判可能造成不必要的担忧。

{count_table}

![分组样本量](group_counts.png)

图 1 两组总体规模接近，全部数据正类比例约 46%，没有明显的性别数量失衡。测试集各组都有至少 96 条正类和 105 条负类，可计算错误率，但记录数量不等于独立受试者数量。

<!-- pagebreak -->

## 二 实验设计与验证集选择

沿用原项目的 1270/421/420 划分，完全重复的特征记录作为一组分配，实测未跨集合。原数据无用户编号，无法按用户划分。字段映射固定，不学习全体数据的类别或阈值；本实验无缺失值、不按全量 IQR 删除记录。StandardScaler 只在训练集拟合，验证与测试只调用 transform。

为使用二分类 EqualizedOdds 约束，另训逻辑回归基线（C=1，max_iter=3000），保留全部 19 维输入，包括性别与年龄。约束方案使用同一种支持 sample_weight 的分类器。它与原型七分类随机森林是不同实验，不把两者成绩直接比较，也不把删除敏感字段当成公平性证据。

ExponentiatedGradient 的优化参数 eps 固定 0.01、max_iter=50；改变的是 EqualizedOdds 的 difference_bound。该约束比较同一真实标签内各组与整体的预测正类率偏差，与报告中组间最大减最小的 EO 指标不是同一上限。[2]

预设选型规则：验证集平衡准确率与 F1 相对基线下降均不超过 2 个百分点，在合格方案中优先取 EO 差值最小者；并列时依次取平衡准确率较高、约束上限较小者。2 个百分点只是课程实验的性能容忍线，不是临床可接受标准。

{val_table}

![验证集约束强度比较](validation_tradeoff.png)

图 2 五种设置的验证指标完全重合，按并列规则锁定 {summary['selection']['selected']}。选型后不重新拟合训练加验证集，保留原训练模型，随后才进行测试评价。原项目此前已评价过这份测试划分，因此它并非从未被查看的外部盲测集；本次未据测试成绩调整模型或参数网格。

<!-- pagebreak -->

## 三 同一测试集上的改进前后对比

两种模型都在相同的 420 条测试记录上评价。Fairlearn MetricFrame 同时计算整体和分组指标，另用 equalized_odds_difference 与 demographic_parity_difference 汇总差值。约束方案调用 predict(random_state=42)，使用其随机混合策略，不额外给混合输出设阈值。

{metric_table}

![整体性能与公平性比较](test_comparison.png)

图 3 左侧指标越高越好，右侧越低越好；两轴量程不同，分别阅读。测试预测逐条一致，整体正确 417 条、错误 3 条。

{performance_table}

平衡准确率是正类召回率与负类召回率的平均；F1 是正类精确率与召回率的调和平均。本表 F1 不同于原七分类报告的宏 F1。女性组本次全部正确，男性组成绩稍低；不能用接近 99% 的整体准确率替代分组判断。

<!-- pagebreak -->

## 四 漏判 误判与不确定性

{error_table}

漏判率 FNR = FN / 正类数 = 1 − TPR；误判率 FPR = FP / 负类数。EO 差值取 TPR 组间差与 FPR 组间差中较大者。本次分别为 0.0208 和 0.0083，故 EO 为 0.0208。男性组的两条正类更容易在本次样本中被漏判，但尚不能推断性别导致了这些错误。

![群体错误率与区间](group_rates.png)

图 4 点为估计值，线为 95% Wilson 区间。为了看清接近边界的数值，左右轴分别放大到 0.90–1.01 和 −0.005–0.065。女性组 FPR 虽为 0，其区间上限仍为 {baseline_female.fpr_high:.2%}；零错误不是零风险保证。缺少正类或负类时相关指标留空，分母少于 30 时标注不稳定；30 只是展示提醒，并非可靠性的充分条件。

{error_example_table}

行号从处理数据第一条记录起计为 1，便于对照 features.csv；BMI 仅用于描述，原标签没有被重新计算。这三条错误在约束方案下均未修正。

测试集真实正类比例为女性 48.53%、男性 44.44%，相差 4.08 个百分点；预测正类比例相差 4.55 个百分点。因此 DP 差值的一部分与标签构成有关，不能仅凭正类预测率不同认定不公平。

<!-- pagebreak -->

## 五 为什么没有改善及其取舍

训练集基线 EO 差值为 {train_rows[0]['equalized_odds_difference']:.4f}；Fairlearn 约束实际检查的最大“组对整体”偏差为 {gamma_max:.4f}，已低于最严格的 0.01。所测试的约束没有迫使模型明显改变判定边界，这是未改善结果的直接线索。选中模型的混合权重为 {weights}，只有一个有效分量，100 个固定随机种子得到的测试 EO 均为 {seed_rows.equalized_odds_difference.min():.4f}，没有观察到预测随机波动。

在这次实验里，原先成绩较低的男性组没有获得改善，女性组也没有被降低表现来换取更小差值。整体性能变化为零，满足预先设定的 2 个百分点容忍线；但零性能损失不等于有公平性收益。因此没有证据支持用当前约束方案替换基线，更不能说模型已对所有人公平。

对固定测试预测，按性别组内做 1000 次成对 Bootstrap，两模型平衡准确率、F1、EO 差值的变化区间均为 [0, 0]。原因是两模型逐条预测相同，重采样后差值必然为零；这不是“真实世界群体差异为零”的区间。它不包含重新训练、不同数据抽样、标签偏差和合成样本相关性带来的不确定性。

### 数据与结论的边界

1. UCI 数据来自墨西哥、秘鲁和哥伦比亚，约 23% 为直接采集、77% 为 SMOTE 合成记录。[1] 本项目没有可用于逐条排除合成样本的可靠标记。生成方法可能改变各组边界与错误分布，误差区间也依赖独立记录假设。
2. 肥胖等级与体重、身高高度相关，本次把相邻的三个肥胖等级合并，使任务比原七分类更容易。较高成绩可能主要反映标签规则，不能推断健康风险或未来减重效果。
3. 标签和问卷可能存在测量或定义偏差。EO 以标签为比较依据，标签有偏差时，较小 EO 也不等于没有伤害；不同类型错误的现实代价也可能不同。
4. 两组样本规模接近，但测试集只有三次错误，个别记录就能改变差值。没有按年龄或性别×年龄细分，也没有外部人群验证。
5. 审核使用全部 19 维输入。原型的七分类表单省略两个字段并作中位数填充，当前公平性结论不直接覆盖该输入简化方式。

后续可以在新的验证方案中探索更严格的约束、增加真实受试者数据并审核交叉群体。本次看过测试结果后没有继续改网格来追求更好数字；后续若根据这些发现改方案，应另留最终评价数据。约束是否改善不预设结论，应同时检查较差群体是否受益、另一组是否被拉低及错误成本是否可接受。

<!-- pagebreak -->

## 六 审核界面与用户理解评价

原型侧栏新增“模型公平性审核”，支持切换女性、男性或全部群体，选择平衡准确率、F1、TPR、FNR、FPR 和预测正类比例，查看同一测试集的基线与约束方案。全局 EO 不随展示筛选重新计算，以免把只显示一组误解为“差值为零”。

页面同时展示正负类数量、真实标签比例、错误率区间和验证集选型依据。说明使用“标签为正类却被判成负类”等短句解释错误；“理解自测”要求区分整体成绩与分组表现。原有体重管理页面仍可切回使用。

![审核页面](audit_page.png)

图 5 实际运行的审核页面。这里的浏览器和自动测试只验证功能，不构成真人理解测试成绩。

用户评价设四项任务：找到两组样本与标签比例；比较漏判和误判；判断约束是否改善；解释为什么整体约 99% 仍不能说明群体一致。测试指南和个人报告模板位于 user_test/；记录每项操作状态、真实用时、提示前后回答。T4先保留首次回答，再打开理解自测。

已收到P01、002、003的评测及后续补充，真人参与性质按用户确认登记。原记录、计时声明与代码核对意见分别保留。本节汇总能够从材料支持的发现，不把任务编号相同直接当作任务内容相同。

<!-- pagebreak -->

### 已收到的评测与理解情况

| 来稿 | 可保留的发现 | 评价限制 |
| --- | --- | --- |
| P01 | 首次反馈指出术语、图例和数值不变时的操作疑虑；后续提供四项操作及时间。 | 首次T1使用全量而非测试集；关于无偏和部署的判断过强。后续通过率、合规状态、Pareto曲线不在指定版本中。 |
| 002 | 分组样本与错误数大多对应冻结结果；指出样本筛选范围容易混淆，能解释整体指标会掩盖组间错误及零错误不能外推。 | 提前看过参考答案。部分步骤涉及不存在的敏感属性或模型切换；不能把其回答记为无提示首次理解。 |
| 003 | 自由走查能指出整体成绩需要结合群体差异；对漏判和误判的含义有一次求助，建议让说明更靠近指标。 | 原T2把两类错误的较高群体分开描述，与男性两项均较高不符。T3/T4为扩展任务，后续补做为体重页面，未覆盖公平性四项任务。 |

对“整体准确率高是否说明各组表现一致”，材料呈现了不同情况：002在已看答案后能作出区分；003的自由回答也提到了整体指标可能掩盖差异，但读取错误归属仍有问题；P01据约2%的差值给出没有系统性偏见的结论，超出了本次样本所能支持的范围。因此不能只根据报告中的“理解”自评就认定三人均掌握该区别，也没有证据证明界面让初次使用者获得了理解提升。

时间方面，P01首次原报545秒、后续281秒；002首次2/3/3/4分钟已明确为估计或示例，后续原报410秒；003自由走查的27分钟为估计，后续体重任务原报1270秒。这些数字属于不同轮次、不同任务，部分操作尚不能对应页面，故不合并计算平均时间，也不把估计分钟换算后作为实测秒数。

三份材料已经收齐，但统一标准任务的完成率、无提示理解正确率和平均操作时间尚未形成。后续核对或补测应保留原始计时、首次回答和已有答案暴露，缺失字段保持缺失。此前体重原型反馈不替代公平性页评价。

<!-- pagebreak -->

### 改进建议、实施状态与评价局限

| 类型 | 根据反馈采取或建议的改进 | 当前状态与检验方式 |
| --- | --- | --- |
| 测试文档 | 将四项固定题干直接放进模板；标明task_sheet.md属于第一次作业；自由探索与补测另记。 | 已落实。后续收回记录时检查是否仍出现任务错配；现有材料不能证明错配已减少。 |
| 界面 | 在样本统计表附近说明它由“数据范围”控制；在指标旁突出错误数、正负类分母。 | 当前已有解释与计数表，位置和显著程度仍可改进。需让新使用者自行找到并解释，不能以看过答案后的正确回答替代。 |
| 界面 | 让两方案同时展示、数值可能相同的说明更醒目；帮助读者把区间、样本量和错误数联系起来。 | 指南已说明数值不变也据实记录，页面已有区间解释。尚未实施新的视觉调整或检验其效果。 |
| 模型评价 | 增加独立真实人群数据，检查错误集中在哪些记录和群体；新约束仍在验证集选择。 | 本次男性三条错误均未改善。外部验证与交叉群体审核属后续工作，不能用界面优化替代模型证据。 |

本轮评价只有三个代号，测试经验和参考答案暴露不一致；部分记录来自自由探索，部分操作无法对应指定版本。反馈可用于定位术语、筛选范围和测试材料的问题，但不足以比较不同界面的易用性，也不能推广到没有技术背景的所有使用者。

后续应在同一运行版本上补齐四项任务的实际操作，先保存首次回答再帮助。已有走查者按后续测试记录；如需评价初次理解，应另邀请未看过答案的使用者。收回材料后分别汇总操作完成、理解和用时，不用模型99%的成绩代替用户评价。

<!-- pagebreak -->

## 七 复核文件与来源

代码包保留训练、验证、测试的中间结果，报告图表由同一批 CSV 生成。逐条预测中的 row_id 为 features.csv 的零起始索引，案例表展示时加 1；性别编码为 Female=0、Male=1。

| 文件 | 可复核的内容 |
| --- | --- |
| data/processed/features.csv | 原始标签、编码特征和固定划分 |
| reports/fairness/group_counts.csv | 每组规模、正负类数和标签比例 |
| reports/fairness/selection.json | 参数网格、性能容忍线、验证集选型和数据哈希 |
| reports/fairness/validation_comparison.csv | 基线和五种约束强度的验证结果 |
| reports/fairness/test_group_metrics.csv | 整体与分组性能、混淆计数和 Wilson 区间 |
| reports/fairness/test_predictions.csv | 基线与约束方案在同一测试样本上的判定 |
| reports/fairness/constraint_diagnostics.json | 训练时组对整体偏差与最终混合权重 |
| reports/fairness/test_summary.json | 测试指标、固定模型与成对 Bootstrap 差值区间 |

复现实验依次运行 python -m src.fairness train、python -m src.fairness evaluate、python -m src.fairness_report。详细环境和启动步骤见《公平性实验运行说明》。为避免覆盖原结果，建议在另一个解压副本中操作。

### 参考资料

[1] UCI 544，Mendoza Palechor 与 De la Hoz Manotas，2019。https://doi.org/10.24432/C5H31Z 。许可 CC BY 4.0，本项目进行编码、划分及模型训练。

[2] Fairlearn 0.13 EqualizedOdds 文档：https://fairlearn.org/v0.13/api_reference/generated/fairlearn.reductions.EqualizedOdds.html 。MetricFrame 文档：https://fairlearn.org/v0.13/api_reference/generated/fairlearn.metrics.MetricFrame.html 。

所有分组 CSV、逐样本预测、验证集选择与图表保存在代码包 reports/fairness/。AI 辅助资料查找、文档整理和代码核验；实验数字来自实际运行，未补写真人测试。本实验仅用于课程学习，不作为医疗诊断依据。
'''
    (OUTPUT / "公平性分析报告.md").write_text(report, encoding="utf-8")
    print(f"公平性图表和报告正文：{OUTPUT}")


if __name__ == "__main__":
    generate()
