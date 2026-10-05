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