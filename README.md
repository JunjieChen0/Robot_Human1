# WeightTrend（暂定名）

**人机交互课程作业选题 2：减重趋势分析原型**

用户自报身高、体重记录、运动量和饮食，原型展示体重趋势、能量平衡估算和肥胖等级估计，并说明预测的适用范围与不确定性。

> **当前进度：混合路线已锁定，数据流水线、模型与交互原型已实现并通过测试。** 用户真实测试记录仍需由课程小组实际完成，不能用示例数据代替。

## 1. 交互设想

```text
录入身高 / 体重记录 / 运动量 / 饮食
          ↓
校验字段、格式与合理范围
          ↓
体重趋势图 + 能量平衡估算（摄入 - 消耗）
          ↓
肥胖等级估计与解释、适用范围说明
          ↓
修改录入 → 重新计算 → 对比结果
```

与作业 1 的关键区别：体重趋势部分直接基于用户自己的多次记录，是描述性分析，不依赖训练数据；需要训练数据支撑的模型部分见下节数据源结论。

## 2. 公开数据调研结论（2026-10-05）

| 候选 | 类型 | 规模 | 字段覆盖 | 许可 | 结论 |
| --- | --- | --- | --- | --- | --- |
| [UCI 544 Estimation of obesity levels based on eating habits and physical condition](https://archive.ics.uci.edu/dataset/544/estimation+of+obesity+levels+based+on+eating+habits+and+physical+condition) | 横断面个体级 | 2111 × 17 | 身高、体重、饮食习惯（FAVC/FCVC/NCP/CH2O/SCC）、运动频率 FAF、肥胖等级标签 | CC BY 4.0 | **推荐**：模型部分主数据，输入结构与原型录入项一致 |
| [CDC BRFSS Nutrition, Physical Activity and Obesity](https://catalog.data.gov/dataset/nutrition-physical-activity-and-obesity-behavioral-risk-factor-surveillance-system) | 横断面调查（聚合） | 大 | 饮食、运动、体重状态 | ODbL | 备选：人群趋势背景，不适合个体建模 |
| NHANES（膳食 24h 回顾 + PAQ + 体格测量） | 横断面个体级 | 大 | 膳食、运动、身高体重 | 公开 | 备选：清洗成本高，收益不明确 |
| 纵向个人体重 + 饮食 + 运动日志 | 时间序列 | — | — | — | **未找到公开可用数据**；趋势部分改为用户自报记录的描述性分析 + 能量平衡模型外推 |

调研要点：

- 同时含「纵向体重记录 + 饮食 + 运动」的公开数据集不存在（检索覆盖 UCI、Kaggle、data.gov、PhysioNet 方向与量化自我文献），因此趋势分析不能建立在公开训练数据上。
- UCI 544 的输入项（身高、体重、饮食行为、运动频率）与原型录入项一一对应，且带肥胖等级标签，可直接支撑作业要求的训练/验证/测试与模型比较。
- 能量平衡部分采用 Mifflin-St Jeor 基础代谢 + 活动系数 TDEE + 动态能量平衡外推，参数来自公开文献，不需要数据集。

## 3. 实测结果（2026-10-05）

| 环节 | 结果 |
| --- | --- |
| 数据规模 | 2111 × 17，缺失 0，完全重复行 16（保留并记录，不机械删除） |
| 划分 | 按标签分层 60/20/20 = 1266 / 422 / 423；无受试者编号，不做分组划分 |
| 验证集比较 | RandomForest macro-F1 0.9402，LogisticRegression 0.8586，选中 RandomForest |
| 测试集评价 | Accuracy 0.9433，macro-F1 0.9426，错误样本 24 / 423 |
| 自动测试 | `pytest -q` 14 通过 |

趋势外推不依赖训练数据：记录期变化由用户自报体重记录直接计算，未来 90 天外推由能量平衡模型给出，并在界面上标注假设与局限。

## 4. 待决问题

- [x] 模型路线锁定：UCI 544 分类 + 能量平衡外推的混合路线。
- [ ] 趋势外推的验证方式（公开纵向数据缺失，需向课程说明验证口径）。
- [x] 原型录入项与 UCI 544 字段的映射表（见 `src/config.py` 的 `FIELD_DESCRIPTIONS_ZH`）。
- [ ] 至少 3 名同学的真实用户测试及改进建议。

## 5. 运行计划

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python -m src.download_data   # 下载并解压 UCI 544
python -m src.preprocess      # 编码、质量检查、分层划分
python -m src.train           # LR vs RF 验证集比较，保存最终模型
python -m src.evaluate        # 测试集指标、混淆矩阵、演示档案
streamlit run app.py          # 启动交互原型
pytest -q                     # 运行自动测试
```
