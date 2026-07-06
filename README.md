# The AI Agent Handbook
## AI Agent 实战手册

Practical, receipted patterns for building AI agents. No guesswork.

Every entry is a standalone atom: situation, forces, the move, a real receipt. You can read it in two minutes and apply it the same day — whether you've never touched AI or you're architecting multi-agent systems at scale.

---

## 如何阅读本书 / How to Read This

- **Start anywhere.** Entries are numbered and cross-linked. Jump to what you need.
- **Trust the receipts.** Every technique ships with a real run log — actual output, actual errors. If there is no receipt, the entry says so.
- **Talk to it.** [Ask Claude Code to navigate this handbook for you.](#talk-to-the-handbook)
- **Contribute.** See something wrong, missing, or stale? [Fork and submit a PR.](CONTRIBUTING.md)

---

## 🔥 优先阅读 / Priority Reads

> **基础编码已死，技能三角是最急迫、溢价最高的入场券。**
> Agent 编排 + RAG + LLM 评估 = 当前市场最供不应求的技能组合。

- [w10 · 技能三角：Agent编排 + RAG + LLM评估](workspace/w10-skill-triangle.md) — ⭐ *先读这个*
- [w11 · AI大厂最稀缺的10项技能](workspace/w11-top-10-ai-skills.md) — 薪资溢价最高的技能清单
- [S-05 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) — Agent 编排核心
- [S-07 · RAG](stacks/s07-rag.md) — 检索增强生成
- [F-02 · Evaluation at Scale](forward-deployed/f02-evaluation-at-scale.md) — LLM 评估

---

## 🇨🇳 中文用户指南 / Chinese Users

**本书适合谁？**
- 想进入 AI 大厂（腾讯、字节、OpenAI 等）的工程师
- 想让自己的 AI 能力产生业务价值的产品经理
- 想从"代码搬运工"升级为"AI 协同创造者"的开发者

**如何用中文提问本书？**
直接用中文问 Claude Code 或任何 AI 助手，例如：

> "帮我找 Agent 编排相关的章节"
> "RAG 的生产级实现方案有哪些？"
> "LLM 评估有哪些实战技巧？"
> "我想做 AI Agent 开发，从哪个章节开始？"
> "哪些技能组合最有市场价值？"

**技能三角路线图（按优先级）：**
```
第一步 → Agent 编排（S-05, F-05, F-06）
第二步 → RAG 检索增强（S-07, F-101~F-107）
第三步 → LLM 评估（F-02, S-193）
第四步 → AI 安全与 Guardrails（F-04, F-10）
第五步 → MLOps / LLMOps（S-100~S-109）
```

---

## Structure

| Book | What it covers |
|---|---|
| [The Laws](laws.md) | The fixed worldview everything hangs from |
| [Book of Stacks](stacks/) | Agent architectures, patterns, and the code that builds them |
| [Book of the Workspace](workspace/) | Tooling, environment, the AI dev setup |
| [Book of the Forward-Deployed Engineer](forward-deployed/) | Shipping AI to real users, evaluating at scale |
| [Book of the Frontier](frontier/) | Research, model landscape, open questions |

---

## Talk to the handbook

If you have Claude Code, run `/handbook` in your terminal to query entries by topic.

Or just ask any capable LLM:

```
You are navigating The AI Agent Handbook at https://github.com/stancsz/handbook.
The handbook is organized into: Laws, Book of Stacks, Book of the Workspace,
Book of the Forward-Deployed Engineer, and Book of the Frontier.
Each entry follows: Name / Situation / Forces / The move / Receipt / See also.
Help me find entries relevant to: [your question]
```

---

## Contribute

Fork → write an entry or fix one → submit a PR. See [CONTRIBUTING.md](CONTRIBUTING.md).

The only rule: if you can't back it with a real receipt, mark it `Receipt pending`.
