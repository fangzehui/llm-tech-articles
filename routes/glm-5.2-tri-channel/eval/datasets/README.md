# 评测数据集准备说明

为避免在仓库内打包外部数据集，本目录**不包含**原始数据，仅放置说明与下载脚本。
请按下述步骤把以下两个 benchmark 的子集放进本目录：

## 1. GSM8K（小学数学应用题）

- 官方仓库：<https://github.com/openai/grade-school-math>
- HuggingFace 镜像：<https://huggingface.co/datasets/gsm8k>

下载 `test.jsonl` 后另存为 `gsm8k_test.jsonl` 即可（一行一题，含 `question` 与 `answer` 两个字段）。

最小样例（每行一个 JSON 对象）：

```json
{"question": "Janet's ducks lay 16 eggs per day...", "answer": "...#### 18"}
```

## 2. HumanEval（Python 代码补全）

- 官方仓库：<https://github.com/openai/human-eval>
- HuggingFace 镜像：<https://huggingface.co/datasets/openai_humaneval>

下载后另存为 `humaneval_test.jsonl`，每行至少包含 `prompt` 字段。

最小样例：

```json
{"task_id": "HumanEval/0", "prompt": "from typing import List\n\n\ndef has_close_elements(...):\n    ...", "canonical_solution": "..."}
```

## 3. 文件清单

```
datasets/
├── README.md                # 本文件
├── gsm8k_test.jsonl         # 自行下载，仅取前 20 条用于快速回归
└── humaneval_test.jsonl     # 自行下载，仅取前 20 条用于快速回归
```

`run_eval.py` 默认只读前 20 条样本。如果想跑完整集，把 `--limit` 调大即可。

## 4. 许可与归属

GSM8K 与 HumanEval 均由 OpenAI 发布，分别遵循各自仓库声明的许可（MIT / Apache 2.0）。
本仓库不分发这些数据，仅以脚本方式调用本地副本。
