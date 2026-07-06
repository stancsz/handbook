# w10 · 技能三角：Agent 编排 + RAG + LLM 评估

基础编码已死。真正值钱的是把大模型变成能干活、能负责、能量化的 AI Agent 的能力。

## Forces

- 大模型本身免费或廉价，但让它稳定干活需要工程能力
- 市场两极分化：会"调 API"的遍地都是，能做 Agent 编排 + 评估的人极度稀缺
- 60% 的企业 AI 应用将包含 Agent，但能设计这套架构的人不超过 5%
- 黄仁勋说的"AI 不会取代人类，但使用 AI 的人会取代不使用 AI 的人"已经发生

## The move

掌握技能三角 — 三项能力互相咬合，单独一项价值有限，三项叠加产生护城河：

```
Agent 编排 ──→ 靠 RAG 提供知识 ──→ 靠 LLM 评估保证质量
     ↑                                       │
     └───────────────────────────────────────┘
```

### 第一极：Agent 编排（Architect）

知道什么时候该拆 Agent、什么时候该合并、如何设计 Agent 间的通信协议和容错。

核心问题：
- 什么粒度拆？单步工具调用 vs 多步子 Agent
- Agent 之间共享状态还是独立？
- 失败后谁来重试、谁来回滚？
- 如何防止 Agent 陷入循环？

参考章节：S-05 · Multi-Agent Patterns、F-05 · Agent Failure Taxonomy、F-06 · Agent Sandboxing

### 第二极：RAG 检索增强（Knowledge）

让 Agent 知道它该知道的东西。私有知识库、企业文档、实时数据的接入能力。

核心问题：
- 检索什么？chunk size、embedding 模型、召回率
- 如何处理结构化数据（表格、数据库）？
- 知识更新后如何刷新索引？
- 如何区分"相关"和"正确"？

参考章节：S-07 · RAG、F-101~F-107 系列

### 第三极：LLM 评估（Quality）

Agent 输出的质量如何量化？如何持续监控？如何自动发现回归？

核心问题：
- 评估指标怎么定义？准确率？幻觉率？延迟？成本？
- 谁来评？LLM-as-Judge 还是人工？
- 如何建立评测基准（golden dataset）？
- 线上回归如何自动告警？

参考章节：F-02 · Evaluation at Scale、S-193 · LLM-as-Judge Eval Pipeline、F-07 · Evaluation-Driven Development

## 这三角为什么值钱

| 能力单独看 | 叠加后的效果 |
|---|---|
| 会调 API | 遍地都是，不值钱 |
| 会 Agent 编排 | 能做简单流水线 |
| 会 RAG | 能接入知识 |
| 会评估 | 能保证质量，但不知道给谁用 |
| **Agent 编排 + RAG + 评估** | **能独立交付一个生产级 AI 应用，这是大厂最缺的人** |

## 入门路径

```
第一步：Agent 编排
  → S-05 Multi-Agent Patterns（通读）
  → F-05 Agent Failure Taxonomy（理解失败模式）
  → F-06 Agent Sandboxing（理解隔离）

第二步：RAG 检索增强
  → S-07 RAG（核心原理）
  → F-101~F-107（生产级细节）

第三步：LLM 评估
  → F-02 Evaluation at Scale（入门）
  → S-193 LLM-as-Judge（自动化评估）
  → F-07 Evaluation-Driven Development（工程实践）

并行：MLOps 基础
  → S-100~S-109（成本监控、日志、灰度）
```

## See also

[S-05 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) · [S-07 · RAG](stacks/s07-rag.md) · [F-02 · Evaluation at Scale](forward-deployed/f02-evaluation-at-scale.md) · [S-193 · LLM-as-Judge Eval Pipeline](stacks/s193-llm-as-judge-eval-pipeline.md) · [w11 · AI大厂最稀缺的10项技能](workspace/w11-top-10-ai-skills.md)