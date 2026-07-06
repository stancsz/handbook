# w11 · AI 大厂最稀缺的 10 项技能

市场两极分化已发生：顶尖 AI 人才被亿元年薪争夺，普通技术人薪资回落至两年前水平。

## Forces

- 大厂不计成本抢人，CEO 亲自监控 LinkedIn 抢人
- 调薪幅度 35% vs 整体技术调薪仅 4%
- 基础编码岗位正被 AI 加速替代
- 真正稀缺的是能设计、交付、量化 AI 系统的人，不是会"调 API"的人

## The move — Top 10 技能排名

以下技能按市场稀缺程度和薪资溢价排序，数据来源：2025-2026 年招聘市场、薪资报告、行业观察。

### 🥇 #1 AI Agent 设计 & 编排 — $150K–$250K

**为什么最值钱：** 60% 的企业 AI 应用将包含 Agent，但能做架构设计的人严重短缺。

- 设计 Agent 间的通信协议和容错机制
- 决定何时拆解 Agent、何时合并
- 实现长期记忆、工具编排、任务分解
- 参考：[S-05](stacks/s05-multi-agent-patterns.md)、[F-05](forward-deployed/f05-agent-failure-taxonomy.md)

### 🥈 #2 大模型微调 (Fine-tuning) — 超 2.3 万/月（中位）

**为什么最值钱：** 大厂不计成本抢有实战经验的人，GPU 资源+数据工程+训练调优三项能力合一者极缺。

- LoRA / QLoRA / DPO 微调方法
- 训练数据构建和清洗
- 评测和迭代
- 参考：[r03 · Fine-tuning vs Prompting](frontier/r03-fine-tuning-vs-prompting.md)

### 🥉 #3 RAG 检索增强生成 — 高薪

**为什么最值钱：** 几乎所有企业 AI 应用都依赖私有知识库，RAG 是刚需能力。

- 向量检索 + 稀疏检索混合
- 重排序（Reranking）
- 知识图谱增强 RAG
- 参考：[S-07](stacks/s07-rag.md)

### #4 LLM 评估与质量保障 — 高薪

**为什么最值钱：** Agent 落地最大的瓶颈是可靠性，能量化 AI 质量的人极度稀缺。

- LLM-as-Judge 评估体系
- 自动化回归测试
- 幻觉检测、毒性检测
- 参考：[F-02](forward-deployed/f02-evaluation-at-scale.md)、[S-193](stacks/s193-llm-as-judge-eval-pipeline.md)

### #5 提示词工程（高级）— 高薪

**为什么值钱：** 不是"会聊天"，是能设计复杂工作流、多轮对话、Chain-of-Thought、Few-shot 策略。

- 结构化提示设计
- 动态提示注入
- 提示版本管理和 A/B 测试

### #6 MLOps / LLMOps — 高薪

**为什么值钱：** 模型部署、监控、成本优化的工程能力，AI 系统从 Demo 到生产的关键环节。

- 模型版本管理
- Token 成本监控
- 灰度发布和回滚
- 参考：[S-100~S-109](stacks/) 系列

### #7 AI 安全与 Responsible AI — 高薪

**为什么值钱：** 合规、伦理、幻觉治理成为监管重点，懂安全又能落地的工程师极缺。

- Prompt 注入防御
- 输出过滤和毒性检测
- 数据隐私合规
- 参考：[F-04 · Guardrails](forward-deployed/f04-guardrails.md)、[F-10 · Agent Identity and Access](forward-deployed/f10-agent-identity-and-access.md)

### #8 多模态模型应用 — 超 2.3 万/月

**为什么值钱：** 图、文、视频、音频联合建模是新战场，能落地多模态应用的人极少。

- Vision-Language Model 接入
- 跨模态检索
- 多模态 Agent

### #9 数据工程（AI 方向）— 高薪

**为什么值钱：** 数据质量决定 AI 上限，能为 AI 构建高质量数据集的人比算法工程师更稀缺。

- 合成数据生成
- 评测数据标注
- 数据质量监控
- 数据偏见检测

### #10 AI 产品管理 — 高薪

**为什么值钱：** 懂 AI 又能定义产品价值、衡量 AI ROI 的人极少，比纯算法人才更稀缺。

- AI 产品指标设计
- AI 功能的价值评估
- 用户体验与 AI 能力的平衡

## 核心结论

```
基础编码  ̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶̶死了

技能三角：Agent 编排 + RAG + LLM 评估 = 最急迫、溢价最高的入场券
```

**破局三条路：**
1. 从"代码搬运工" → "AI 协同创造者"，用 AI 赋能业务创新
2. 深耕技能三角，形成组合壁垒
3. 卡位细分场景：AI 安全合规、垂直行业 AI、AI Agent 工程化落地

## See also

[w10 · 技能三角：Agent编排 + RAG + LLM评估](workspace/w10-skill-triangle.md) · [S-05 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) · [S-07 · RAG](stacks/s07-rag.md) · [F-02 · Evaluation at Scale](forward-deployed/f02-evaluation-at-scale.md) · [r03 · Fine-tuning vs Prompting](frontier/r03-fine-tuning-vs-prompting.md)