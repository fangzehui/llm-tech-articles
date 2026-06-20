# Chapter 17 - Prompt Cache 五家成本横评

本目录是文章《[17 Prompt Caching 成本实测横评](../../17-Prompt_Caching成本实测横评.md)》的配套示例代码。

## 核心概念

- **五家计费四件套建模**：Anthropic Claude Sonnet 4.5 / Claude Fable 5 / OpenAI GPT-5 / Google Gemini 3 Pro / 智谱 GLM-5.2 / DeepSeek V3.2，每家给出 `input` / `output` / `cache_write` / `cache_read` 四个核心单价 + 触发机制 + TTL 元信息
- **Scenario 描述长系统提示词复用场景**：`system_prompt_tokens` × `num_calls`，外加每次的 `user_tokens` / `output_tokens` 与请求间隔
- **三档 TTL 策略**：`default` / `5m_renew` / `1h`，覆盖 Anthropic 5min × N 续命与 1h 一把锁的常见对比
- **break-even 模型**：从第几次轮询开始，cache 总成本严格低于不开 cache —— 在典型 8K 系统提示场景下 6 家厂商全部在第 2 次回本

## 文件清单

| 文件 | 说明 |
|------|------|
| `cache_bench.py` | `PriceTable` + `PRICE_TABLES` + `Scenario` + `cost_no_cache` / `cost_with_cache` / `compare_all` / `break_even` + main demo |
| `test_smoke.py` | pytest 风格 7 个用例：价目表完整性、无 cache 基准、Anthropic 5min 计费、break-even、横评排序、5min vs 1h TTL、key 一致性 |
| `requirements.txt` | 仅 pytest（运行测试时需要） |

## 快速开始

```bash
pip install -r requirements.txt
python cache_bench.py            # 跑 demo，打印 8K 系统提示 × 100 次轮询的横评 + break-even
pytest test_smoke.py -q          # 跑 smoke test
```

## 输出示意

```
=== 场景：长系统提示 8K × 100 次轮询 ===
  system=8000 tok / user=200 tok / output=200 tok / calls=100 / 间隔 0.5 min

模型                      无cache$    有cache$       省$      省比例  机制
  Gemini 3 Pro           0.9000     0.1872   0.7128    79.2%  cached_contents
  Claude Sonnet 4.5      2.7600     0.6276   2.1324    77.3%  explicit_cache_control
  Claude Fable 5         9.2000     2.0920   7.1080    77.3%  explicit_cache_control
  GLM-5.2                0.5320     0.1360   0.3960    74.4%  auto_prefix
  GPT-5                  1.2250     0.3340   0.8910    72.7%  auto_prefix
  DeepSeek V3.2          0.0794     0.0350   0.0444    55.9%  disk_kv

=== break-even 分析（第几次开始 cache 净回本）===
  Claude Sonnet 4.5  break-even = 2 次
  Claude Fable 5     break-even = 2 次
  GPT-5              break-even = 2 次
  Gemini 3 Pro       break-even = 2 次
  GLM-5.2            break-even = 2 次
  DeepSeek V3.2      break-even = 2 次

=== 5min × N 续命 vs 1h 一把锁（间隔 6 min）===
  Claude Sonnet 4.5  5m_renew=$3.3600 (写100次) | 1h=$0.6456 (写1次)
  Claude Fable 5     5m_renew=$11.2000 (写100次) | 1h=$2.1520 (写1次)
```

## 配套文章

- [17-Prompt_Caching成本实测横评.md](../../17-Prompt_Caching成本实测横评.md)

## 数据声明

`PRICE_TABLES` 中的单价摘自各厂商官方定价页（截至 2026-06-19），具体来源链接见正文 §三。
其中 Claude Fable 5、GLM-5.2 与 DeepSeek V3.2 等本系列前置文章使用的"前瞻型号"价格保持与 14 / 13 / 02 号文一致；
真实生产环境请以厂商控制台实时显示为准。

模型层面的"renew_count"采用了简化二档判定（间隔 < TTL 视为 1 次写入；间隔 ≥ TTL 视为 num_calls 次 miss），
覆盖了绝大多数轮询型场景。如需更精细的"突发请求 + 部分续命"建模，可在 `_compute_renew_count` 上自行扩展。
