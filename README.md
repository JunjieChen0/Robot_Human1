# WeightTrend（暂定名）

**人机交互课程作业选题 2：减重趋势分析原型**

> **受邀参加第二次作业测试的同学，请从这里开始：**
> [公平性页面测试指南](user_test/fairness_test_guide.md)包含启动方法、四项任务和报告提交要求。
> 复制[个人测试报告模板](user_test/fairness_report_template.md)，完成后把填写的 Markdown 文件发回邀请你测试的同学即可。
> 只测试该页面不需要下载数据或训练模型。请先按指南测试，再阅读下方实验结果，避免影响首次回答。

用户自报身高、体重记录、运动量和饮食，原型展示体重趋势、能量平衡估算和肥胖等级估计，并说明预测的适用范围与不确定性。

> **当前进度：原型和性别公平性审核页均已实现，自动测试共 34 条通过。**
> 三名同学的测试记录及提交文档保存在本地 `commit/`，不随 Git 克隆分发；本轮界面修改后尚未开展真人复测。`user_test/` 保留后续测试用的空白模板。
>
> 提交材料第 1 项「数据来源说明、可运行代码及运行说明」在本仓库内的载体即 §2（数据来源）、§3（模型与效果）与 §5（运行说明）。

## 1. 任务定义：目标用户、使用场景与输入输出

**目标用户**：有减重/体重管理需求、希望了解自身能量平衡与体重变化趋势的普通人群，特别是健康管理初学者。原型定位为**教学演示与自测工具**，不作为医疗诊断依据。

**使用场景**：用户在家庭或课堂环境中录入自身体重记录、运动量与饮食信息，原型回答三类问题：

1. 我目前的体重状态属于哪个肥胖等级？（分类预测）
2. 我的体重在记录期内变化趋势如何？（描述性分析）
3. 按当前能量平衡，未来体重大致会向哪个方向变化？（解析外推）

**输入数据**：性别、年龄、身高、体重、饮食习惯（蔬菜摄入评分 1–3、主餐次数、高热量饮食、加餐频率、饮酒频率）、运动频率评分 0–3、生活方式（出行方式、吸烟、家族超重史、是否记录热量摄入）——原型表单共采集 **14 个字段**。

**未采集字段的处理**：模型训练时包含「每日饮水量（CH2O）」与「电子设备使用时间（TUE）」两项，但原型不再向用户采集，以简化录入，预测时由模型按**训练集中位数**填充（CH2O = 2.0、TUE = 0.634），保证输入仍为完整的 19 维特征。经实测，7 个演示档案在该口径下仍全部判定正确；该取值口径已在界面使用说明与特征重要性表中披露。

**界面结构**：录入表单按语义分为「🧍 身体基本信息」「🥗 饮食习惯」「🏃 运动与生活方式」三张卡片，每行 4 列填满；蔬菜摄入量、高热量饮食与运动频率带问号详细说明；结果区采用概率表 + 柱状图双栏布局。

**输出**：7 类肥胖等级的概率分布、记录期体重趋势图、按 Mifflin-St Jeor 基础代谢 + 活动系数 TDEE 计算的每日能量差与 90 天体重外推。

交互流程：

```text
录入身高 / 体重记录 / 运动量 / 饮食
          ↓
校验字段、格式与合理范围
          ↓
体重趋势图 + 能量平衡估算（消耗 - 摄入）
          ↓
肥胖等级估计与解释、适用范围说明
          ↓
修改录入 → 重新计算 → 对比结果
```

体重趋势部分直接基于用户自己的多次记录，是描述性分析，不依赖训练数据；需要训练数据支撑的模型部分见下节数据源结论。

## 2. 数据来源与处理结论

### 2.1 公开数据调研结论（2026-10-05）

| 候选 | 类型 | 规模 | 字段覆盖 | 许可 | 结论 |
| --- | --- | --- | --- | --- | --- |
| [UCI 544 Estimation of obesity levels based on eating habits and physical condition](https://archive.ics.uci.edu/dataset/544/estimation+of+obesity+levels+based+on+eating+habits+and+physical+condition) | 横断面个体级 | 2111 × 17 | 身高、体重、饮食习惯（FAVC/FCVC/NCP/CH2O/SCC）、运动频率 FAF、肥胖等级标签 | CC BY 4.0 | **采用**：模型部分主数据，输入结构与原型录入项一致 |
| CDC BRFSS Nutrition, Physical Activity and Obesity | 横断面调查（聚合） | 大 | 饮食、运动、体重状态 | 本项目未核验 | 未采用 |
| NHANES（膳食 24h 回顾 + PAQ + 体格测量） | 横断面个体级 | 大 | 膳食、运动、身高体重 | 本项目未核验 | 未采用 |
| 纵向个人体重 + 饮食 + 运动日志 | 时间序列 | — | — | — | **未找到公开可用数据**；趋势部分改为用户自报记录的描述性分析 + 能量平衡模型外推 |

调研要点：

- 本项目未获得适合直接使用的个人纵向体重、饮食与运动数据，不能据此断言此类公开数据不存在；趋势模块使用自报记录与简化能量外推。
- UCI 544 的输入项（身高、体重、饮食行为、运动频率）与原型录入项一一对应，且带肥胖等级标签，可直接支撑作业要求的训练/验证/测试与模型比较。
- 能量平衡部分采用 Mifflin-St Jeor 静息能量估算、固定活动系数与线性外推；公式可直接计算，但个体预测误差仍需纵向数据评价。

### 2.2 数据质量与异常值处理

- 数据规模：原始 CSV 为 2111 行 × 17 列（16 个属性 + 1 个标签列），缺失 0，非有限值 0；MTRANS one-hot 展开为 4 个哑变量后，模型输入为 **19 维特征**。
- 完全重复行：33 行分属 9 个重复组，其中冗余 24 行（`data/processed/data_quality.json` 的 `duplicate_full_rows`）。**保留不删除**，划分时按组整体分配，避免完全重复行跨集合（实测 0 组跨划分）；该检查不能排除相近合成样本的影响。
- 异常值检测（`src/preprocess.py::detect_outliers`）：
  - **问卷字段**（FCVC/NCP/CH2O/FAF/TUE）取值本身是问卷语义（如 FAF 0–3 表示每周运动频率等级），只做领域边界校验，结果**无领域非法值**；
  - **连续字段**（Age/Height/Weight）额外报告 IQR 离群点（Age 168、Height 1、Weight 1），这些属于分布尾部而非数据错误，**保留全部样本**，不机械删除或截尾。
  - 完整报告见 `reports/tables/outlier_summary.json`。
- 数据局限（报告中需说明）：UCI 544 的问卷部分来自哥伦比亚/秘鲁/墨西哥人群，其余大部分为 SMOTE 合成扩充样本（据数据集论文），类别边界可能比真实人群干净，**0.94 量级的准确率存在一定乐观偏差**。

## 3. 模型与效果评价（2026-10-06 更新）

| 环节 | 结果 |
| --- | --- |
| 数据规模 | 原始 2111 × 17（编码后 19 维特征），缺失 0，重复 9 组 33 行 / 冗余 24 行（保留并按组划分，不机械删除） |
| 划分 | 按标签分层 60/20/20 = 1270 / 421 / 420；无受试者编号，不做用户分组；重复行按组整体划分，无跨划分泄漏 |
| 验证集比较 | RandomForest macro-F1 0.9569，LogisticRegression 0.8625，选中 RandomForest |
| 测试集评价 | Accuracy 0.9452，macro-F1 0.9438，错误样本 23 / 420 |
| 特征重要性 | Weight 0.326、Height 0.097、Age 0.095 居前（模型高度依赖体重/身高/年龄信号） |
| 自动测试 | `pytest -q` 34 通过（含公平性扩展） |

按原型的中位数填充方式另行评价，同一测试集准确率为 93.10%、宏 F1 为 0.9293；完整特征评价仍为 94.52%、0.9438。结果见 `reports/tables/prototype_input_metrics.json`。

### 3.1 错误案例分析（`reports/tables/error_analysis.md`）

- 错误率 5.5%（23/420），错误最多的真实类别是**超重 I 级**（7 条）。
- 错误集中在**相邻 BMI 等级边界**（正常体重 ↔ 超重 I 级），符合类别边界样本预期。
- 错误样本平均体重比正确样本低约 8.8 kg；两组类别构成不同，不能把这一均值差直接解释为误判原因，也不能据此比较不同单位字段的重要性。
- 约 52% 的错误样本最高概率落在 40%–70% 区间，这只是错误子集的概率分布，不能据此推断所有样本的错误率。
- 可能原因：边界样本特征组合落在决策边界附近；数据含 SMOTE 合成样本，边界模式可能不完全反映真实人群；概率分布平坦时轻微特征变化即可改变预测。

### 3.2 趋势外推的验证口径

本项目未采用纵向训练数据，趋势模块不依赖分类训练集：记录期变化由用户自报体重记录直接计算，未来 90 天外推由**解析能量平衡模型**给出（7700 kcal 折合 1 kg，每日能量差恒定假设），曲线包含第 90 天终点。`tests/test_energy.py` 检查公式参考值、活动系数阈值、能量差方向和外推终点；这些测试不能替代真实预测误差评价。界面标注结果仅用于趋势参考，不作为医学诊断。

活动水平由运动频率字段 FAF（数据集取值 0–3）映射，档位阈值为 1/3/5，因此在当前录入范围内**「高度活动」不可达**，最高只能得到「中度活动」（1.55 系数），该映射为原型采用的简化假设，尚未验证个体误差。该口径已在界面 FAF 字段说明中披露；若要放开上限，需同时调整 `src/energy.py` 的档位阈值并重算外推数值。

## 4. 待决问题

- [x] 模型路线锁定：UCI 544 分类 + 能量平衡外推的混合路线。
- [x] 趋势外推的验证方式：公开纵向数据缺失，采用**解析自洽验证 + 界面明示示意性口径**（见 §3.2，迭代 3/5）。
- [x] 原型录入项与 UCI 544 字段的映射表（见 `src/config.py` 的 `FIELD_DESCRIPTIONS_ZH`）。
- [x] 异常值处理：检测 + 论证保留，报告见 `reports/tables/outlier_summary.json`（迭代 2）。
- [x] 错误案例分析：脚本 `src/error_analysis.py` 与报告 `reports/tables/error_analysis.md`（迭代 3）。
- [x] 三人测试记录与改进建议已整理到本地 `commit/`；本轮界面修改后的真人复测尚未开展。`user_test/` 保留空白模板。

## 5. 运行说明

### 5.1 环境要求

| 项 | 要求 | 实测通过版本（2026-10-09） |
| --- | --- | --- |
| Python | 3.11 | 3.11.15 |
| 依赖 | 见 `requirements.txt`（范围约束，未提供 lock 文件） | streamlit 1.65.0、scikit-learn 1.9.0、pandas 2.3.3 |
| 网络 | **首次运行需要联网**访问 `archive.ics.uci.edu` 下载数据集；离线兜底见 §5.5 | — |

### 5.2 运行体重管理原型需要重建的产物

`.gitignore` 排除了三类可由脚本重建的本地产物。克隆后若要使用体重管理页面或复现实验，按 §5.3 重建；只参加公平性页面用户测试时，按[测试指南](user_test/fairness_test_guide.md)安装依赖并启动即可：

| 路径 | 内容 | 由哪一步生成 |
| --- | --- | --- |
| `data/raw/` | UCI 544 官方压缩包与原始 CSV | `python -m src.download_data` |
| `data/processed/` | `features.csv`（19 维编码 + `split` 列）、`data_quality.json` | `python -m src.preprocess` |
| `models/` | `final_model.joblib`、`model_metadata.json`、`raw_ranges.json` | `python -m src.train` |

已入库、无需重建的产物：`reports/tables/*`、`reports/figures/*`、`data/sample/demo_profiles.csv`。
缺少模型文件时 `app.py` 会打印缺失清单与重建命令后停止，不会崩溃。

### 5.3 运行步骤

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python -m src.download_data   # 下载并解压 UCI 544        → data/raw/
python -m src.preprocess      # 编码、质量检查、异常值报告、分层划分 → data/processed/
python -m src.train           # LR vs RF 验证集比较，保存最终模型   → models/
python -m src.evaluate        # 测试集指标、混淆矩阵、演示档案      → reports/
python -m src.error_analysis  # 错误案例分析报告            → reports/tables/error_analysis.md
streamlit run app.py          # 启动交互原型（默认 http://localhost:8501）
pytest -q                     # 运行自动测试
```

步骤有先后依赖：`train` 读 `data/processed/features.csv`，`evaluate` 与 `error_analysis` 读 `models/final_model.joblib`，`error_analysis` 还读 `evaluate` 产出的 `reports/tables/test_predictions.csv`。完整自动测试和体重管理页面需要 `models/` 与 `data/sample/` 已就位；公平性审核页面只读取已入库的 `reports/fairness/`，无需这些模型文件。

### 5.4 成功判据

| 检查项 | 期望结果 |
| --- | --- |
| `pytest -q` | **34 passed**，退出码 0 |
| `python -m src.train` 标准输出 | RandomForest macro-F1 **0.9569** > LogisticRegression **0.8625**，最终模型为 RandomForest |
| `python -m src.evaluate` 标准输出 | accuracy **0.9452**、测试样本 **420**、错误 **23**（macro-F1 0.9438 见 `reports/tables/test_classification_report.csv`） |
| 原型服务 | `http://localhost:8501/_stcore/health` 返回 `ok` |
| 原型端到端（默认档案直接提交） | 正常体重 / 最高概率 47.0% / 差值 12.3% / 轻度活动 / 每日消耗 2037 kcal / 能量差 +237 kcal |

`RANDOM_STATE = 42`（`src/config.py`）固定了划分与训练随机性，按上述顺序重跑应复现同样的指标。

### 5.5 离线环境兜底

无网络时 `src.download_data` 会重试 3 次后失败，并在报错信息中给出手动步骤：

1. 从 §2.1 表中的 UCI 544 官方链接下载压缩包；
2. 保存为 `data/raw/uci544.zip`；
3. 重新运行 `python -m src.download_data`——脚本检测到有效压缩包后跳过下载，直接解压到 `data/raw/uci544/`；
4. 解压后必须存在 `data/raw/uci544/ObesityDataSet_raw_and_data_sinthetic.csv`；若压缩包内部结构不同，脚本会报错并打印该期望路径，按路径手动放置即可。

数据就位后，`src.preprocess` 及之后的所有步骤都是本地计算，不再需要网络。

---

迭代过程记录见 `CHANGELOG.md`（基线快照 → 正确性修复 → 数据处理规范性 → 效果评价补全 → 原型改进 → 文档汇总 → 精简录入项 → 界面重设计 → 提交路径修复 → 字段口径修正 → 运行说明补全 → 交付文档汇编 → 交付文档改本地件），每次迭代（含小版本修复）都会追加条目并同步文末「当前状态」表。

## 公平性扩展作业

参加用户测试请按[公平性页面测试指南](user_test/fairness_test_guide.md)操作，并返回[个人测试报告](user_test/fairness_report_template.md)。[记录者说明](user_test/fairness_facilitator_guide.md)含核对依据，由组织测试的同学使用。以下内容用于实验复现，不是测试者必须执行的步骤。

侧栏选择“模型公平性审核”可查看分组样本、基线与约束方案、漏判率与误判率、区间及解释。该实验将肥胖 I–III 型合并为正类，按原数据的性别分组；它是独立的二分类审核，不替代原七分类和能量外推。

```powershell
python -m src.fairness train
python -m src.fairness evaluate
python -m src.fairness_report
python -m pytest -q
python -m streamlit run app.py
```

先准备处理数据；若从 Git 克隆，按原流程下载、预处理，并为体重页面训练和评价原模型。新实验的 StandardScaler 和两种二分类模型仅在训练集拟合，验证集选择约束上限，测试集用于冻结后的评价。约束网格为 0.01、0.02、0.05、0.10、0.20；验证集平衡准确率和 F1 各允许最多下降 0.02，在合格方案中优先选 EO 差值较小者。

实测选中 eo_0.01；基线与约束方案在 420 条测试记录上逐条预测相同，平衡准确率均为 0.992650，F1 为 0.992288，EO 差值为 0.020833。女性本次零错误，男性漏判 2 次、误判 1 次。实验没有改善群体差异，报告说明了训练约束已满足等原因；不以高整体成绩或零性能损失宣称公平。

审核产物在 reports/fairness/，本地提交材料在 commit/公平性作业/。生成图表和 Markdown 正文用 src.fairness_report，PDF 是随包提供的排版版本。运行依赖新增 Fairlearn 0.13.0，其 SciPy 约束由 pip 解析。新增页面的真人理解测试尚待开展，user_test/fairness_records.csv 是空表，旧的三份体重原型反馈不能替代此次测试。
