# WeightTrend 迭代日志

本文件按迭代阶段记录项目的改进过程，供课程审查迭代历史使用。每个阶段包含：日期、改动文件、验证方式与指标前后对比。

## 迭代 0：基线快照（2026-10-06）

**动作**：重跑完整流水线（preprocess → train → evaluate），确认产物可复现；运行 `pytest -q`。

**验证结果**：

| 项 | 基线值 |
| --- | --- |
| pytest | 14 passed |
| 验证集模型比较 | RandomForest macro-F1 0.9402 > LogisticRegression 0.8586 |
| 测试集 accuracy | 0.9433（423 样本，错误 24 条） |
| 测试集 macro-F1 | 0.9426 |
| 概率列 argmax 还原 `predicted` 率 | **28.4%**（异常，阶段 1 修复） |
| 重复行 | 33 行 / 9 组，其中 **6 组跨 split**（阶段 2 修复） |

**结论**：基线产物可复现，模型指标正常；但报告 CSV 的概率列名与数值错位、重复样本组跨划分，需在后续迭代修复。

---

## 迭代 1：正确性修复（2026-10-06）

**改动**：
- `src/evaluate.py`：概率列名改用 `model.named_steps["classifier"].classes_`（字母序）命名，修复 `predict_proba` 列序与 `LABEL_ORDER`（语义序）不一致导致的 5 个概率列名错位
- `requirements.txt`：`streamlit>=1.30,<2` → `streamlit>=1.49,<2`（代码使用 1.49+ 的 `width="stretch"` API）
- `src/validation.py`：修正重复日期警告文案（原"仅保留排序后的全部记录"自相矛盾）
- `tests/test_validation.py`：新增重复日期警告用例
- `src/preprocess.py`：不再产出 `data/processed/raw_ranges.json`（由 `src.train` 统一写 `models/raw_ranges.json`），删除该重复维护路径

**验证**：

| 项 | 迭代 0 | 迭代 1 |
| --- | --- | --- |
| 概率列 argmax 还原 `predicted` 率 | 28.4% | **100.0%** |
| pytest | 14 passed | **15 passed** |
| 测试集 accuracy / macro-F1 | 0.9433 / 0.9426 | 0.9433 / 0.9426（不受影响） |

**结论**：报告概率列已正确，测试套件扩展至 15 条；模型指标无变化（本次仅修复报告与配置）。

---

## 迭代 2：数据处理规范性（2026-10-06）

**改动**：
- `src/preprocess.py`：新增 `detect_outliers()` 异常值检测与 `OUTLIER_LIMITS` 领域边界表
  - 问卷字段（FCVC/NCP/CH2O/FAF/TUE）只做领域边界校验：其取值范围本身就是问卷语义，IQR 会把合法边界值误报为离群点
  - 连续字段（Age/Height/Weight）额外报告 IQR 离群点数量
  - 产出 `reports/tables/outlier_summary.json`，并把摘要写入 `data_quality.json`
- `src/preprocess.py`：重写 `assign_splits()`，完全重复的行按组整体划分（leader 行参与分层，组内成员跟随），消除跨划分泄漏
- `tests/test_preprocess.py`：新增领域越界检测用例与重复组同划分用例

**验证**：

| 项 | 迭代 1 | 迭代 2 |
| --- | --- | --- |
| 重复组跨 split | 6 组 | **0 组**（9 组 33 行全部同划分） |
| 划分规模 | 1266 / 422 / 423 | 1270 / 421 / 420（按组划分后的新分层） |
| 领域越界值 | — | **0**（无领域非法值，保留全部样本） |
| Age / Height / Weight 的 IQR 离群 | — | 168 / 1 / 1（分布尾部，非错误值） |
| pytest | 15 passed | **17 passed** |
| 验证集 RF macro-F1 | 0.9402 | 0.9569 |
| 测试集 accuracy / macro-F1 | 0.9433 / 0.9426（423 样本） | **0.9452 / 0.9438（420 样本，错误 23）** |
| 概率列 argmax 还原率 | 100.0% | 100.0% |

**说明**：模型指标变化来自两处——(1) 重复组按组划分改变了 train/test 组成；(2) 消除了跨划分重复样本。Age 的 IQR 离群点 168 个（年龄 35–61 岁的合法样本）恰好佐证了"问卷/健康数据不能机械套用 IQR 截尾"的结论，因此保留全部样本并在报告中论证。

---

## 迭代 3：效果评价补全（2026-10-06）

**改动**：
- 新增 `src/error_analysis.py`：读取 `test_predictions.csv`，自动生成错误分布表、错误/正确样本特征均值对比、典型错误案例与数据驱动观察，产出 `reports/tables/error_analysis.md`
- `tests/test_model.py`：新增用例验证"概率列必须按 `classes_` 命名而非 `LABEL_ORDER`"，防止报告列名问题回归

**错误分析结论（写入报告）**：
- 错误率 5.5%（23/420），错误最多的真实类别是**超重 I 级**（7 条）
- 错误集中在相邻 BMI 等级（正常体重 ↔ 超重 I 级），符合"类别边界样本"预期
- 错误样本与正确样本差异最大的特征是**体重**（均值差 -8.8 kg），说明边界样本的体重处于类别过渡区
- 约 52% 的错误样本最高概率落在 40%–70% 区间，模型在这些样本上置信度不足

**验证**：pytest **18 passed**（新增 1 条）。

**说明**：趋势外推的验证口径（解析自洽 + 明示示意性）将在迭代 5 写入 README 待决问题。

---