# Research Evidence — Beimingwu Chapter 34

调研主题：北冥坞（Beimingwu）学件基础设施技术方向前沿进展与真实应用案例
生成时间：2026-07-14 CST
规则：一事一块；8 字段（claim / source_name / source_url / source_type / publication_date / retrieval_date / confidence / notes）；关键数字必须带数据日期。

---

## §1 核心论文（2024-2026）

### E1.1 Dali 规约（ICML 2025）
- claim: 东南大学 Chen Wei / Mao Jun-Xiang / Wang Xiaozheng / Zhang Min-Ling 于 ICML 2025 发表 "Learnware Specification via Dual Alignment"，将学件规约设计为"对齐用户任务分布" + "对齐模型能力"双视角。
- source_name: PMLR v267 Proceedings of ICML 2025
- source_url: https://proceedings.mlr.press/v267/chen25as.html
- source_type: 一手学术出版物
- publication_date: 2025-07 (ICML 2025 Vancouver, 会议接收)
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 页码 8683-8699；PDF 直链 https://raw.githubusercontent.com/mlresearch/v267/main/assets/chen25as/chen25as.pdf ；对齐机制为"user-side alignment + model-side alignment"两条支路。

### E1.2 NTK-RKME 规约（计算机学报 2024）
- claim: 谭志豪、史浩宇、陈梓轩、姜远发表《基于神经切线核的学件 RKME 规约》，用 NTK 内核替换 RBF/线性核以让 RKME 规约在深度网络场景下更贴近模型行为。
- source_name: 《计算机学报》2024 年第 47 卷第 6 期
- source_url: http://cjc.ict.ac.cn/online/onlinepaper/tzh-2024612163911.pdf
- source_type: 一手学术出版物
- publication_date: 2024-06
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 页码 47(6):1232-1243；出版方中国科学院计算所；用于第 33 号已简述，第 34 号做进阶技术解读用。

### E1.3 LLM 学件（arXiv:2505.13425）
- claim: 谭志豪等提出 100 个 8B 小模型组成"LLM 学件坞"，通过规约选取 + LoRA 参数向量组合，实现金融 14 数据集平均分 63.87→66.60（+2.73），并在 Open Medical LLM Leaderboard 上超越 Flan-PaLM-540B（排名第 7）。
- source_name: arXiv 2505.13425
- source_url: https://arxiv.org/abs/2505.13425
- source_type: 一手预印本
- publication_date: 2025-05-19
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 基座 Llama3.1-8B / Qwen2.5-7B；规约 SLM=Qwen2.5-0.5B；每个学件 LoRA 参数向量 <1M；金融 Table A8 详细逐数据集对比；数学 Table A9 均分 Qwen2.5-7B 51.68 / Learnware 组合 52.62 / Oracle 上界 54.89 / Qwen1.5-110B 57.99；HTML 版本 https://arxiv.org/html/2505.13425v1/ 。

### E1.4 异构决策树学件组装（计算机研究与发展 2026）
- claim: 谭鹏、周志华发表《基于决策树的异构特征空间学件组装方法》，针对表格类学件在异构特征空间下的组装难题（如医疗 MIMIC 26 张表 / OMOP CDM 场景），提出决策树结构级组装范式。
- source_name: 《计算机研究与发展》2026 年第 63 卷第 5 期
- source_url: http://crad.ict.ac.cn/CN/10.7544/issn1000-1239.202550460
- source_type: 一手学术出版物
- publication_date: 2026-05-01（收稿 2025-06-09 / 录用 2026-01-07 / 刊出 2026-05-01）
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 页码 63(5):1249-1260；DOI:10.7544/issn1000-1239.202550460；CSTR:32373.14.issn1000-1239.202550460；基金：国家自然科学基金 NSFC 62250069；获 CCML 2025 最佳学生论文奖。

### E1.5 Beimingwu 系统（KDD 2024）
- claim: 谭志豪、刘建东、毕晓东、谭鹏等在 KDD 2024 发表《Beimingwu: A Learnware Dock System》，为全球首个针对学件范式研发的开源基础设施，用户提交任务规约即可自动匹配 + 组合 dock 中已有学件。
- source_name: KDD 2024 Proceedings
- source_url: https://dl.acm.org/doi/10.1145/3637528.3671617
- source_type: 一手学术出版物
- publication_date: 2024-08 (KDD'24 Barcelona)
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 页码 5773-5782；DOI:10.1145/3637528.3671617；arXiv 版 https://arxiv.org/abs/2401.14427 ；作者列表 Zhi-Hao Tan*, Jian-Dong Liu*, Xiao-Dong Bi, Peng Tan, Qin-Cheng Zheng, Hai-Tian Liu, Yi Xie, Xiao-Chuan Zou, Yang Yu, Zhi-Hua Zhou。

### E1.6 LANE 判别性规约（AAAI 2025）
- claim: 东南大学陈伟、毛俊翔、张敏灵与中移浙江合作发表 "LANE: Learnware Specification via Local Distinguishable Feature"，提出可判别的局部特征规约，用于用户任务与学件匹配的更细粒度对齐。
- source_name: AAAI 2025 Proceedings
- source_url: https://ojs.aaai.org/index.php/AAAI/article/view/33741
- source_type: 一手学术出版物
- publication_date: 2025-04-11
- retrieval_date: 2026-07-14
- confidence: 高
- notes: AAAI 39(15):15857-15865；DOI:10.1609/aaai.v39i15.33741；产学合作案例（东南大学 + 中国移动浙江）。

### E1.7 AAAI 2026 Tabular Learnware Repurposed
- claim: 谭鹏、杨飞凡、谭志豪、周志华在 AAAI 2026 发表 "Tabular Learnwares Can Be Repurposed"，将现有表格类学件复用到新的任务与结构分布上。
- source_name: AAAI 2026 Proceedings
- source_url: http://www.lamda.nju.edu.cn/tanzh/supp_files/pub/2026-AAAI-Tabular%20Learnwares.pdf
- source_type: 一手学术出版物
- publication_date: 2026-03-14
- retrieval_date: 2026-07-14
- confidence: 高
- notes: AAAI 40(30):25778-25786；DOI:10.1609/aaai.v40i30.39776；LAMDA 官方存档。

### E1.8 IJCAI 2025 不同标签空间学件
- claim: 刘建东、谭志豪、周志华在 IJCAI 2025 就学件系统在不同标签空间下的复用问题给出可扩展解法。
- source_name: IJCAI 2025 Proceedings
- source_url: https://www.ijcai.org/proceedings/2025/0638.pdf
- source_type: 一手学术出版物
- publication_date: 2025-08 (IJCAI'25 Montreal)
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 页码 5734-5742；DOI:10.24963/ijcai.2025/638。

### E1.9 KDD 2025 动态学件过滤
- claim: 刘建东、谭志豪、周志华在 KDD 2025 发表动态学件过滤方法，处理学件坞规模持续增长带来的搜索效率问题。
- source_name: KDD 2025 Proceedings
- source_url: https://dl.acm.org/doi/proceedings/10.1145/3690624
- source_type: 一手学术出版物
- publication_date: 2025-08 (KDD'25 Toronto)
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 页码 1811-1822；DOI 待补；相同一作团队。

### E1.10 NeurIPS 2024 隐私证明与异构特征标签
- claim: 团队在 NeurIPS 2024 有 2 篇 learnware 相关工作：(a) 雷浩仪等《学件坞的隐私证明》pp.36471-36513；(b) 谭鹏、刘海天等《异构特征与标签空间学件复用》pp.12767-12795。
- source_name: NeurIPS 2024 Proceedings
- source_url: https://proceedings.neurips.cc/paper_files/paper/2024
- source_type: 一手学术出版物
- publication_date: 2024-12
- retrieval_date: 2026-07-14
- confidence: 中高
- notes: 两篇论文均在 NeurIPS 37；具体链接需在 NeurIPS 文献索引中检索。

### E1.11 2026 待发表论文（LAMDA 主页公开预告）
- claim: 谭志豪 LAMDA 主页已公开 3 篇 2026 待发表论文：ICLR'26 PAVE 规约、ICML'26 Inversion Risks Framework、IJCAI'26 PAVE Privacy。
- source_name: 南京大学 LAMDA 谭志豪主页
- source_url: http://www.lamda.nju.edu.cn/tanzh/
- source_type: 一手学者官网
- publication_date: 2026-05 (主页最近更新)
- retrieval_date: 2026-07-14
- confidence: 中高
- notes: 主页格式为标准学者出版目录；ICLR'26 一作 Hao-Yu Shi 等，ICML'26 一作 Hao-Yi Lei 等。

---

## §2 Beimingwu KDD'24 benchmark 完整实验数据

### E2.1 表格三数据集实验（Corporacion / PFS / M5）
- claim: KDD'24 表格实验用 Kaggle 三个销售预测数据集 Corporacion、PFS、M5 造 265 个学件，覆盖 5 种特征空间 + 2 种标签空间的异构组合。
- source_name: Beimingwu KDD'24 论文
- source_url: https://arxiv.org/abs/2401.14427
- source_type: 一手学术出版物
- publication_date: 2024-01-25（arXiv v1 提交日）
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 265 学件是当时论文表格实验硬数字；异构表格查搜是北冥坞相对 HuggingFace 的关键差异化。

### E2.2 图像 CIFAR-10 实验
- claim: KDD'24 CIFAR-10 实验：50 个学件，每学件训练在 4 类不平衡 12000 样本（比例 0.4:0.4:0.1:0.1），100 个用户任务各 3000 样本 6 类（0.3:0.3:0.1:0.1:0.1:0.1）；用 1-Acc loss 评价。Mean 基线 0.655 → 单最优学件 0.304 → JobSelector 0.406 → AverageEnsemble 0.310（Ensemble 最优）。
- source_name: Beimingwu KDD'24 论文
- source_url: https://arxiv.org/abs/2401.14427
- source_type: 一手学术出版物
- publication_date: 2024-01-25
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 数据来自论文表格；Top-1 单学件搜索基本已能贴近训练全集的性能。

### E2.3 文本 20-newsgroup 实验
- claim: KDD'24 文本实验：20-newsgroup 数据集，50 个学件，特征 tf-idf + 朴素贝叶斯分类器；Mean 0.493 / 单最优 0.141 / Top-1 搜索 0.154 / JobSelector 0.155 / AverageEnsemble 0.138。
- source_name: Beimingwu KDD'24 论文
- source_url: https://arxiv.org/abs/2401.14427
- source_type: 一手学术出版物
- publication_date: 2024-01-25
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 三场景（表格 / 图像 / 文本）全部数据规模透明，可入报告表。

### E2.4 工业界泵频率控制案例（真实应用四要素）
- claim: KDD'24 工业界案例：Polixir 团队协助的水厂泵频率控制场景，客户使用 10 个历史学件进行组合，能耗从每 1000 吨水 35.1 kWh 降至 31.0 kWh（下降 11.7%），泵出水量维持不变。
- source_name: Beimingwu KDD'24 论文
- source_url: https://arxiv.org/abs/2401.14427
- source_type: 一手学术出版物
- publication_date: 2024-01-25
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 客户/场景/数据规模/效果指标四要素齐全；四要素之"客户"为水厂，"数据"为 10 历史模型 + 泵运行数据流，"指标"11.7% 能耗降幅。

### E2.5 教育科研使用规模
- claim: KDD'24 论文报告已有 500+ 研究者、来自 150+ 高校在北冥坞上开展学件研究。
- source_name: Beimingwu KDD'24 论文
- source_url: https://arxiv.org/abs/2401.14427
- source_type: 一手学术出版物
- publication_date: 2024-01-25
- retrieval_date: 2026-07-14
- confidence: 中高
- notes: 数字为 2024 年 1 月投稿时点数据；截至 2026-07 更新数字未在官网公开找到；报告中标注"截至 2024-01"。

### E2.6 LLM 学件金融 14 数据集详细数字
- claim: arXiv:2505.13425 金融 Table A8 给出 14 项详细数字：Australian 45.68→56.83；LendingClub 84.60→92.07；FiQA-SA 74.90→76.38；FPB 82.17→84.25；German 66.00→67.06；Headlines 92.80→95.61 F1；NER 49.29→52.79；ACL18 49.73→52.82；BigData22 49.76→52.40；CIKM18 49.46→55.99；FinArg-ARC 62.90→64.31；FinArg-ACC 54.41→58.08；MA 75.25→79.81；MultiFin 59.80→63.46；总均分 63.87→66.60。
- source_name: arXiv:2505.13425 (v1)
- source_url: https://arxiv.org/html/2505.13425v1/
- source_type: 一手预印本
- publication_date: 2025-05-19
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 部分基线为 Qwen2.5-7B；对比大模型 Qwen1.5-110B / Qwen2.5-72B / Llama3.1-70B-Instruct 全域被 Learnware 组合方案超越至少 14 分。

---

## §3 开源生态实时数据（截至 2026-07-13 GitHub API）

### E3.1 Learnware-LAMDA/Learnware 仓库
- claim: GitHub 主仓库 Learnware-LAMDA/Learnware：112 stars / 4 forks，主语言 Python，Apache-2.0，最后 push 2025-05-27，仓库大小 19150 KB，主页 https://learnware.readthedocs.io/ ，Topics: learnware / learnware-dock-system / machine-learning / machine-learning-platform。
- source_name: GitHub REST API
- source_url: https://api.github.com/repos/Learnware-LAMDA/Learnware
- source_type: 一手 API 数据
- publication_date: 2026-07-13（API 快照）
- retrieval_date: 2026-07-13
- confidence: 高
- notes: 星标数字对比 HuggingFace 各主流仓库仍属小规模；活跃度以 commit + issue 为主，非社交传播。

### E3.2 Learnware-LAMDA/Beimingwu 前端仓库
- claim: GitHub 前端展示仓库 Learnware-LAMDA/Beimingwu：124 stars / 4 forks，主语言 Vue，Apache-2.0，最后 push 2024-07-17。
- source_name: GitHub REST API
- source_url: https://api.github.com/repos/Learnware-LAMDA/Beimingwu
- source_type: 一手 API 数据
- publication_date: 2026-07-13
- retrieval_date: 2026-07-13
- confidence: 高
- notes: 前端更新节奏慢于核心库；核心 Python 库仍在维护。

### E3.3 PyPI 发行版
- claim: `learnware` Python 包最新版本 0.4.0.post1，2025-05-25 发布，维护者 Lucius-Liu。
- source_name: PyPI
- source_url: https://pypi.org/project/learnware/
- source_type: 一手包管理仓库
- publication_date: 2025-05-25
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 半年一次的版本迭代；说明团队保持轻量维护节奏。

### E3.4 官网与文档
- claim: 北冥坞官方系统 https://bmwu.cloud/ 与官方文档 https://docs.bmwu.cloud/en/ 提供表格 / 图像 / 文本三种数据类型学件的提交、检索、组合能力；v1.0 于 2024 年 1 月发布。
- source_name: docs.bmwu.cloud 版本页
- source_url: https://docs.bmwu.cloud/en/versions.html
- source_type: 一手官方文档
- publication_date: 2024-01
- retrieval_date: 2026-07-14
- confidence: 高
- notes: v1.0 是里程碑；异构表格查搜为差异化亮点；国内镜像 https://www.gitlink.org.cn/beimingwu 。

### E3.5 R&D 团队构成
- claim: 官方文档披露研发团队包含周志华、俞扬、谭志豪、刘建东、谭鹏、毕晓东、郑钦程、邹晓川、谢懿、刘海天、史浩宇、张昕宇；早期原型成员 Lan-Zhe Guo / Zi-Xuan Chen / Zhi Zhou / Yi-Xuan Jin。
- source_name: docs.bmwu.cloud 关于页
- source_url: https://docs.bmwu.cloud/en/about-us.html
- source_type: 一手官方文档
- publication_date: 2024-01 起持续更新
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 团队实名可查；对论文一作／通讯有清晰追溯。

---

## §4 三范式对标数据

### E4.1 HuggingFace 规模数据（2025-10-27）
- claim: HuggingFace 官方博客宣布 huggingface_hub v1.0 发布，同步公布规模：200 万+ 公开模型、50 万+ 数据集、100 万+ Spaces、月下载量 1.135 亿、累计下载 16 亿、日活 6 万+、月活 55 万+、企业用户 20 万+、总注册用户 1300 万。
- source_name: HuggingFace 官方博客中文版
- source_url: https://huggingface.co/blog/zh/huggingface-hub-v1
- source_type: 一手厂商公告
- publication_date: 2025-10-27
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 用于第 33 号 "点评+范式对比" 之外的规模量级对标；Model Zoo 已是"海量组件超市"级别。

### E4.2 ModelScope 规模数据（2025-09-29）
- claim: 阿里云栖大会 2025 公布 ModelScope 模型数突破 10 万、用户 1800 万、覆盖 200+ 国家、5000+ MCP 服务。
- source_name: ModelScope 官方 Learn 中心
- source_url: https://www.modelscope.cn/learn/1994
- source_type: 一手厂商公告
- publication_date: 2025-09-29
- retrieval_date: 2026-07-14
- confidence: 高
- notes: HuggingFace 与 ModelScope 均是"上传即分享"的传统 Model Zoo，与"规约驱动检索 + 组合"模式的北冥坞正好形成对照。

### E4.3 Model Spider 学术竞品（NeurIPS 2023）
- claim: NeurIPS 2023 Yi-Kai Zhang / Ting-Ji Huang / Yao-Xiang Ding / De-Chuan Zhan / Han-Jia Ye 发表 "Model Spider: Learning to Rank Pre-Trained Models Efficiently"，采用嵌入式召回 + 学习排序的方式，从 Model Zoo 中挑选合适预训练模型。
- source_name: NeurIPS 2023 Proceedings
- source_url: https://proceedings.neurips.cc/paper_files/paper/2023/hash/2c71b14637802ed08eaa3cf50342b2b9-Abstract-Conference.html
- source_type: 一手学术出版物
- publication_date: 2023-12
- retrieval_date: 2026-07-14
- confidence: 高
- notes: NeurIPS 36 pp. 13692-13719；南大 LAMDA 相邻团队（Han-Jia Ye）；与北冥坞"规约 + 匹配"范式相似但语义规约更弱，属"内嵌向量代理"路线，可作为学术竞品。

### E4.4 联邦学习 vs 学件（原则差异）
- claim: 联邦学习是"多方数据不出本地"共同训练一个中心模型；学件是"多方模型公开、规约无泄漏、按需组合"，两者共享"数据隐私不出手"，但学件不需要多方联合训练轮次，只在推理侧做规约匹配组合。
- source_name: Zhou & Tan (SCIS 2024) Learnware 综述
- source_url: https://link.springer.com/article/10.1007/s11432-023-3818-1
- source_type: 一手学术综述
- publication_date: 2024-01
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 第 33 号已简要提及；本次进一步做"训练态 vs 推理态""同步 vs 异步""语义规约"三个维度延伸对标。

### E4.5 LoRA / Adapter 差异
- claim: LoRA (Hu et al. ICLR 2022) 与 Adapter (Houlsby ICML 2019) 在同一基座模型上做低秩 / 瓶颈参数插件，学件则是模型级插件；学件规约是"选哪个模型"，LoRA 权重是"如何贴合任务"，两者理论上互补。
- source_name: LoRA 原论文 arXiv:2106.09685
- source_url: https://arxiv.org/abs/2106.09685
- source_type: 一手学术出版物
- publication_date: 2021-06 / 2022-01 ICLR
- retrieval_date: 2026-07-14
- confidence: 高
- notes: arXiv:2505.13425 恰恰把两者结合——每个 8B 学件封装 LoRA 参数向量，规约层承担选取；报告中要强调"学件 = LoRA-as-Learnware"是自然升维。

---

## §5 国际影响与荣誉

### E5.1 周志华当选中国科学院院士
- claim: 2025-11-21 中国科学院公布新增院士名单，周志华当选信息技术科学部院士；南京大学官网同日发文祝贺。
- source_name: 南京大学官网新闻
- source_url: https://www.nju.edu.cn/info/1055/448751.htm
- source_type: 一手机构公告
- publication_date: 2025-11-21
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 学件范式提出者当选院士，是北冥坞学术站位的重要背书；周志华 1973-11 生于贵阳，籍贯江苏盐城，贵阳六中 1992 届；2024 年任南京大学副校长；IJCAI Trustee 主席（首位中国大陆学者）。

### E5.2 澳门大学 2025 学件讲座
- claim: 澳门大学 2025-03-25 举办周志华 "Learnware Paradigm" 主题讲座；澳门科技大学同日授予荣誉博士学位并邀请其做反绎学习讲座。
- source_name: 澳门大学官方新闻
- source_url: https://fst.um.edu.mo/
- source_type: 一手学术活动记录
- publication_date: 2025-03-25
- retrieval_date: 2026-07-14
- confidence: 中高
- notes: 用于国际影响维度；报告中标注"港澳地区"。

### E5.3 MEET 2025 keynote
- claim: 2024 年 12 月 MEET 2025 智能未来大会，周志华以《学件和异构大模型》为题做主旨演讲。
- source_name: 量子位 MEET 2025 大会公开报道
- source_url: https://www.qbitai.com/
- source_type: 二手行业媒体
- publication_date: 2024-12
- retrieval_date: 2026-07-14
- confidence: 中
- notes: 主流行业媒体报道；不作为一手证据，但可作为"学件 + LLM"叙事的公开讲述节点。

---

## §6 项目局限与开放问题（客观陈述）

### E6.1 GitHub star 规模仍显小众
- claim: 截至 2026-07-13，Learnware 核心库 112 stars / Beimingwu 前端 124 stars，与 HuggingFace/transformers 数十万级 star 存在两个数量级差距。
- source_name: GitHub REST API 快照
- source_url: https://api.github.com/repos/Learnware-LAMDA/Learnware
- source_type: 一手 API 数据
- publication_date: 2026-07-13
- retrieval_date: 2026-07-13
- confidence: 高
- notes: 客观数据；学件仍处于学术原型 + 早期工业验证阶段。

### E6.2 案例真实客户名称与规模缺披露
- claim: KDD'24 泵频率控制案例只披露"能耗-11.7%"与"10 历史学件"，未披露真实客户名称、数据规模（工厂数 / 日均记录数）与部署时长；北冥坞官网亦未提供"客户列表"页。
- source_name: bmwu.cloud 官网
- source_url: https://bmwu.cloud/
- source_type: 一手官网
- publication_date: 持续更新
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 客观事实；本次报告应显式标注"客户名称：未披露"避免脑补。

### E6.3 医疗 / 金融 / 政务 / 司法真实客户级案例
- claim: 除 KDD'24 泵案例外，通过 6 轮 search_web 未找到北冥坞在医疗 / 金融 / 政务 / 司法领域的真实客户级案例（有公开的 客户 / 场景 / 数据规模 / 效果指标 四要素）。arXiv:2505.13425 的金融 / 医疗均为公开 benchmark 结果，不属于"客户级落地"。
- source_name: 综合 search_web 结果
- source_url: N/A
- source_type: 检索归纳
- publication_date: 2026-07-14
- retrieval_date: 2026-07-14
- confidence: 高
- notes: [INFO_GAP] 在最终报告中显式标注；给主 Agent 的可落地案例清单仅列 "泵工业 + 三 benchmark + LLM 学件 + 教育科研" 六个可展开点。

---

## §7 其他辅证

### E7.1 KDD'24 arXiv 版本与页码
- claim: Beimingwu KDD'24 论文的 arXiv 版本号 arXiv:2401.14427，DOI 10.1145/3637528.3671617，KDD Barcelona 会议 pp. 5773-5782。
- source_name: ACM DL / arXiv
- source_url: https://dl.acm.org/doi/10.1145/3637528.3671617
- source_type: 一手学术出版物
- publication_date: 2024-08
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 用于报告"第一手案例来源"引用。

### E7.2 NSFC 62250069 基金
- claim: 决策树异构学件组装论文接受国家自然科学基金 62250069 号资助；周志华为该 61 类原创研究群体项目负责人（学件基础理论）。
- source_name: 计算机研究与发展 DOI 页
- source_url: http://crad.ict.ac.cn/CN/10.7544/issn1000-1239.202550460
- source_type: 一手学术出版物
- publication_date: 2026-05
- retrieval_date: 2026-07-14
- confidence: 高
- notes: 62250069 属于 NSFC 基础科学中心项目类；用于说明"官方持续资助"背书。

### E7.3 CCML 2025 最佳学生论文
- claim: 决策树异构学件组装工作获 CCML 2025 最佳学生论文奖。
- source_name: 计算机研究与发展 DOI 页备注
- source_url: http://crad.ict.ac.cn/CN/10.7544/issn1000-1239.202550460
- source_type: 一手学术出版物
- publication_date: 2025-10
- retrieval_date: 2026-07-14
- confidence: 中高
- notes: 中国机器学习大会 CCML；国内学术共同体对学件方向的认可。
