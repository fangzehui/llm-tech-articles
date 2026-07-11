# chapter-31-sk-hynix-ipo

《SK 海力士纳斯达克 IPO 全解：AI 存储史上第三大 IPO、七月估值震荡与 HBM4 供需锁死》配套源码。承接第 29 篇《大模型时代存储市场复盘 2024-2026》与第 30 篇《AI 存储技术方向硬核解析》，本篇聚焦市场事件侧——2026 年 7 月 10 日 SK 海力士登陆纳斯达克这场"AI 存储史上第三大 IPO"的完整解读。

> 📄 **CSDN 正文链接**：<https://blog.csdn.net/LDZKKJ/article/details/162796704>

## 目录结构

```
chapter-31-sk-hynix-ipo/
├── README.md
├── references.md
└── data-visualization/
    ├── ipo-timeline.py        # SK 海力士 IPO 时间轴（KOSPI 熔断 → 上市 → 切代码）
    ├── ipo-timeline.png       # 时间轴渲染结果（300 DPI）
    ├── hbm4-market.py         # HBM 市占率饼图 + HBM4 溢价柱状图
    └── hbm4-market.png        # 双图渲染结果（300 DPI）
```

## 快速跑通

```bash
pip install matplotlib numpy
cd data-visualization
python ipo-timeline.py    # 生成 IPO 时间轴 PNG
python hbm4-market.py     # 生成市占率 + HBM4 溢价 PNG
```

## 核心数据点速查表

### IPO 首日行情
| 项目 | 数值 | 来源 |
|---|---|---|
| ADR 发行价 | 149 USD/ADS | SK Hynix IR |
| 发行数量 | 1.779 亿份 ADS（每份 = 1/10 普通股） | SK Hynix IR |
| 募资规模 | 约 265 亿美元 | SK Hynix IR |
| 上市首日开盘 | 170 USD | 新华社 / 融中财经 |
| 首日最高 | 177 USD | 融中财经 |
| 首日收盘 | 168.01 USD（+12.8%） | Nasdaq.com |
| 总市值（收盘价） | 约 1.22 万亿美元 | 融中财经 |
| 临时代码 | SKHYV（7-10 起） | SK Hynix IR |
| 正式代码 | SKHY（7-13 起） | SK Hynix IR |
| 认购倍数 | > 7 倍 | Nasdaq.com |
| 参与账户 | > 500 家 | 今日头条 / 大摩 |
| 认购需求总额 | 约 2000 亿美元 | 今日头条 / 大摩 |
| 基石意向单 | 70 亿美元（Baillie Gifford + Coatue + Situational Awareness） | 融中财经 |
| 基石实际获配 | 约 50 亿美元 | 今日头条 |

### 史上 IPO 规模排位
| 排名 | 公司 | 募资规模 | 时间 |
|---|---|---|---|
| 1 | SpaceX | 约 857 亿美元 | 2026-06 |
| 2 | 沙特阿美（含超额配售） | 约 294 亿美元 | 2019 |
| 3 | SK 海力士 | 265 亿美元 | 2026-07 |
| 参考 | 阿里巴巴（原外企赴美 IPO 纪录） | 250 亿美元 | 2014 |

### 7 月 2 日 KOSPI 熔断
| 标的 | 单日跌幅 |
|---|---|
| SK 海力士 | -14.6% |
| 三星电子 | -9% |
| 美光科技（前一日美股） | -10%+ |
| SanDisk / 西部数据 | -7% |

### SK 海力士 Q1 2026 财务
| 指标 | 数值 |
|---|---|
| 单季营收 | 52.58 万亿韩元（YoY +198%） |
| 营业利润 | 37.61 万亿韩元（YoY +405%） |
| 净利润 | 40.35 万亿韩元（YoY +398%） |
| 营业利润率 | 72%（历史最高） |
| 净利率 | 77% |
| 毛利率 | 79.3%（YoY +22pp） |
| HBM 全球市占 | 56.4% |
| 全年 2026 净利润共识 | 221 万亿韩元 / 约 1440 亿美元（YoY +415%） |

### HBM4 供需锁死
- HBM4 合约价：较 HBM3E 溢价约 50%
- 2026 全年 HBM 产能：100% 售罄
- 2027 长协：主流客户已锁定
- 部分高端订单：锁至 2028 年
- DigiTimes 预测：HBM4 价格 2 USD/Gb（2026H2）→ 4-5 USD/Gb（2027），2027 全球 DRAM 一半产能不对小买家开放

## 3 项资源一句话摘要

1. **ipo-timeline.py**：把从 7-02 KOSPI 熔断到 7-10 IPO 上市、7-13 切正式代码 SKHY 的 5 个关键节点画成一条彩色时间轴，用不同颜色区分"市场风险 / 定价动作 / 挂牌动作"三类事件。
2. **hbm4-market.py**：左半张 Counterpoint 口径的 HBM 市占率饼图（SK 海力士 56.4% 领跑），右半张以 HBM3E = 100 为基准的 HBM4 溢价柱状图（2026H2 +50%、2027H1 +125%）。
3. **references.md**：完整参考来源清单，含 SK 海力士 IR 官方公告、新华社 / Nasdaq.com / 融中财经 / PomiNews / DigiTimes / 新浪财经 / 今日头条 / 新浪新闻 共 10 条一手/二手信源，每条带发布时间与 URL。

## 与前后章节的关系

| 章节 | 关系 |
|---|---|
| [chapter-29-llm-storage-market-2024-2026](../chapter-29-llm-storage-market-2024-2026/) | 市场结构底稿，讲"存储市场为什么这么变" |
| [chapter-30-ai-storage-tech-roadmap](../chapter-30-ai-storage-tech-roadmap/) | 技术侧姊妹篇，HBM4/CXL/QLC 六大主线 |
| chapter-31（本篇） | 事件深化，IPO 一手数据 + HBM4 供需锁死收束 |

数据源见每个源文件顶部 docstring 与 `references.md`。截至 2026-07-11 定稿。
