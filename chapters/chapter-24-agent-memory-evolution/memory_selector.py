"""
memory_selector.py — 4 大 Agent 记忆方案（mem0 / Zep / LangMem / Letta）选型脚本

用法：
    python memory_selector.py                    # 交互式
    python memory_selector.py --scenario long_session --users many --graph
    python memory_selector.py --demo              # 跑一遍 6 类典型场景

评分维度（都是 0-3 分）：
    long_session      长会话（>50 轮 / 跨天）
    multi_user        多用户 / 多租户 / 有权限隔离要求
    knowledge_dense   知识密集（需要企业数据 + 会话数据混合）
    graph             需要显式关系推理（谁是谁的老板、哪个产品替代了哪个）
    self_hosted       需要完全自托管（不能上云）
    langchain_stack   已经用 LangGraph / LangChain 全家桶

方案画像来源：
- mem0：Apache 2.0 全栈开源；LOCOMO 66.9%（arxiv 2504.19413）；已被 CrewAI/Flowise 集成
- Zep：Graphiti (Apache 2.0) 开源图核；Zep Cloud 托管 SaaS，SOC2 / HIPAA
- LangMem：LangChain 官方 SDK，跟 LangGraph Store 原生打通
- Letta：MemGPT 论文实现的生产化，OS 风格分层记忆，全开源可自托管
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Solution:
    name: str
    tagline: str
    # 每个维度上的适配得分（0-3）
    scores: Dict[str, int] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)
    watch_out: List[str] = field(default_factory=list)
    repo: str = ""


CATALOG: List[Solution] = [
    Solution(
        name="mem0",
        tagline="工程化最成熟的 memory-as-a-service，Apache 2.0 全栈",
        scores={
            "long_session": 3, "multi_user": 3, "knowledge_dense": 2,
            "graph": 2, "self_hosted": 3, "langchain_stack": 2,
        },
        strengths=[
            "文档 / SDK / 集成生态最完整（CrewAI / Flowise / OpenAI Agents / MCP）",
            "全栈 Apache 2.0，Docker 一键起自托管",
            "Mem0g 变体支持关系图检索",
        ],
        watch_out=[
            "图能力弱于 Zep：单跳 fact 强，复杂多跳推理要靠 Mem0g",
            "抽取质量强依赖你配的 LLM",
        ],
        repo="https://github.com/mem0ai/mem0",
    ),
    Solution(
        name="Zep / Graphiti",
        tagline="Graphiti 双时态图开源 + Zep Cloud 企业托管",
        scores={
            "long_session": 3, "multi_user": 3, "knowledge_dense": 3,
            "graph": 3, "self_hosted": 2, "langchain_stack": 2,
        },
        strengths=[
            "bi-temporal 知识图，天然支持'某时刻的状态是什么'",
            "把业务结构化数据和对话统一进一张图，企业场景强",
            "Zep Cloud 提供 SOC2/HIPAA 合规",
        ],
        watch_out=[
            "自托管只能拿到 Graphiti（Neo4j / FalkorDB / Kuzu 后端）",
            "Zep Cloud 完整栈不开源，有厂商锁定风险",
        ],
        repo="https://github.com/getzep/graphiti",
    ),
    Solution(
        name="LangMem",
        tagline="LangChain 官方长期记忆 SDK，和 LangGraph Store 原生打通",
        scores={
            "long_session": 2, "multi_user": 2, "knowledge_dense": 2,
            "graph": 1, "self_hosted": 2, "langchain_stack": 3,
        },
        strengths=[
            "语义 / 情景 / 程序性三类记忆的原语最清晰",
            "已经在 LangGraph 里的项目零成本接入",
            "命名空间 + 键值 + 向量索引，模型无关",
        ],
        watch_out=[
            "本身不是图数据库，跨实体多跳推理弱",
            "生态强绑定 LangChain 栈",
        ],
        repo="https://github.com/langchain-ai/langmem",
    ),
    Solution(
        name="Letta (原 MemGPT)",
        tagline="OS 风格分层记忆的鼻祖，agent 自主 self-edit 记忆",
        scores={
            "long_session": 3, "multi_user": 2, "knowledge_dense": 2,
            "graph": 2, "self_hosted": 3, "langchain_stack": 1,
        },
        strengths=[
            "in-context / archival / recall 三级分页，符合虚拟内存直觉",
            "agent 自己决定往 core 写什么、什么时候 search archival",
            "全开源、可自部署、有 Agent Development Environment (ADE)",
        ],
        watch_out=[
            "上手门槛比 mem0 高，需要理解 memory block 语义",
            "对图关系推理是通过 archival + tool call 拼出来，不如 Zep 原生",
        ],
        repo="https://github.com/letta-ai/letta",
    ),
]


# 用户场景权重：把 CLI 布尔标志映射成 0-3 的需求强度
def build_requirement(args: argparse.Namespace) -> Dict[str, int]:
    req: Dict[str, int] = {
        "long_session": 0, "multi_user": 0, "knowledge_dense": 0,
        "graph": 0, "self_hosted": 0, "langchain_stack": 0,
    }
    mapping = {
        "long_session": args.scenario == "long_session",
        "multi_user": args.users == "many",
        "knowledge_dense": args.scenario == "knowledge_dense",
        "graph": args.graph,
        "self_hosted": args.self_hosted,
        "langchain_stack": args.langchain,
    }
    # "被明确点名的维度"权重远大于默认，确保方案里"专精"该维度的项目能翻盘
    for k, v in mapping.items():
        req[k] = 6 if v else 1
    return req


def score(sol: Solution, req: Dict[str, int]) -> float:
    return sum(sol.scores.get(k, 0) * w for k, w in req.items())


def recommend(req: Dict[str, int]) -> List[Dict]:
    ranked = [(score(s, req), s) for s in CATALOG]
    ranked.sort(key=lambda x: x[0], reverse=True)
    out = []
    for sc, s in ranked:
        out.append({
            "name": s.name,
            "score": round(sc, 2),
            "tagline": s.tagline,
            "repo": s.repo,
            "strengths": s.strengths,
            "watch_out": s.watch_out,
        })
    return out


# ---------- CLI ----------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Agent 记忆方案选型器")
    p.add_argument("--scenario", choices=["long_session", "knowledge_dense", "generic"],
                   default="generic")
    p.add_argument("--users", choices=["single", "many"], default="single")
    p.add_argument("--graph", action="store_true", help="需要显式关系推理")
    p.add_argument("--self-hosted", action="store_true", help="必须自托管")
    p.add_argument("--langchain", action="store_true", help="已用 LangGraph 栈")
    p.add_argument("--demo", action="store_true", help="跑 6 个典型场景")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    return p.parse_args()


DEMO_CASES = [
    ("个人陪伴 chatbot（单用户 / 长会话）",
     dict(scenario="long_session", users="single", graph=False,
          self_hosted=False, langchain=False)),
    ("企业客服 SaaS（多租户 / 长会话 / 合规）",
     dict(scenario="long_session", users="many", graph=False,
          self_hosted=False, langchain=False)),
    ("投研 Agent（知识密集 / 图关系 / 自托管）",
     dict(scenario="knowledge_dense", users="single", graph=True,
          self_hosted=True, langchain=False)),
    ("LangGraph 内嵌记忆（技术栈锁定）",
     dict(scenario="generic", users="single", graph=False,
          self_hosted=False, langchain=True)),
    ("研究/极客型 Agent（OS 直觉 / 全自托管）",
     dict(scenario="long_session", users="single", graph=True,
          self_hosted=True, langchain=False)),
    ("Coding Agent 全球部署（多用户 / 长会话 / 需要生态）",
     dict(scenario="long_session", users="many", graph=False,
          self_hosted=False, langchain=False)),
]


def print_reco(title: str, req: Dict[str, int], as_json: bool = False) -> None:
    reco = recommend(req)
    if as_json:
        print(json.dumps({"title": title, "req": req, "recommend": reco},
                         ensure_ascii=False, indent=2))
        return
    print("\n" + "=" * 70)
    print(f"场景：{title}")
    print(f"权重：{req}")
    print("-" * 70)
    for i, r in enumerate(reco, 1):
        print(f"  #{i}  {r['name']:20s}  score={r['score']:5.1f}  — {r['tagline']}")
    print(f"→ 推荐首选：{reco[0]['name']}  ({reco[0]['repo']})")
    print(f"   优势：{'; '.join(reco[0]['strengths'][:2])}")


def main() -> None:
    args = parse_args()
    if args.demo:
        for title, kw in DEMO_CASES:
            fake_ns = argparse.Namespace(scenario=kw["scenario"], users=kw["users"],
                                         graph=kw["graph"], self_hosted=kw["self_hosted"],
                                         langchain=kw["langchain"], demo=False, json=False)
            print_reco(title, build_requirement(fake_ns), as_json=args.json)
        return
    print_reco("用户输入", build_requirement(args), as_json=args.json)


if __name__ == "__main__":
    main()
