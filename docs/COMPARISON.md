# Comparison — KoreaSim vs related LLM-agent simulators

> Audience: anyone (HN, Reddit, reviewer) asking *"how is this different from Generative Agents / Social Simulacra / AgentSims / AutoGen?"*
> Last updated: 2026-05-04. Open a PR if any of the four prior systems below has shipped a feature that changes a row in the matrix.

## TL;DR

Four systems are sometimes named in the same breath as KoreaSim. They solve **different problems**:

- **[Park 2022 — Social Simulacra](https://arxiv.org/abs/2208.04024)** generates *forum-shaped text* (posts/replies) so designers can prototype community-design rules.
- **[Park 2023 — Generative Agents (Smallville)](https://arxiv.org/abs/2304.03442)** runs *25 hand-authored characters with memory + reflection + planning* through multi-day simulated lives.
- **[AgentSims (Lin 2023)](https://arxiv.org/abs/2308.04026)** is a *sandbox to evaluate LLM agent capabilities* (memory modules, tool-use) on GUI-built tasks.
- **[Microsoft AutoGen](https://arxiv.org/abs/2308.08155)** is a *programming framework for multi-agent task-solving* (code-gen, problem-solving via dialogue).

KoreaSim's slot is narrower and different: **one news article → N census-grounded personas → demographic-segmented opinion fan-out → maps + JSON.** No memory, no dialogue, no tool-use. The contribution is the **input pipeline** (URL → LLM-summarised structured brief → verbatim quote/number guard → persona fan-out) and the **dataset grounding** (NVIDIA's Nemotron-Personas-Korea, 7M Koreans tied to KOSIS census), not the agent architecture.

If you need believable life-stories or evaluating an agent's tool-use, KoreaSim is the wrong tool. If you need *"what would a demographically representative slice of Korea say about this specific policy/news article, locally and cheaply?"* — that is the gap.

---

## Comparison matrix

| Dimension | [Social Simulacra](https://arxiv.org/abs/2208.04024) (Park 2022, UIST) | [Generative Agents](https://arxiv.org/abs/2304.03442) (Park 2023, UIST) | [AgentSims](https://arxiv.org/abs/2308.04026) (Lin 2023) | [AutoGen](https://arxiv.org/abs/2308.08155) (Microsoft 2023) | **KoreaSim** |
|---|---|---|---|---|---|
| **Primary goal** | Prototype social-computing systems (forums, communities) | Believable proxies of human behavior over days | Sandbox to **evaluate** LLM agent capabilities | Multi-agent **task-solving** programming framework | Demographically-grounded **opinion fan-out** on a single stimulus |
| **Topology** | Multi-user threaded discussion | Multi-agent agent–environment over a 2D map | Multi-agent + GUI-built map + tasks | Multi-agent dialogue, code execution | **One-round, 1 stimulus → N independent agents** |
| **Persona source** | Seed personas → LLM-generated members | Hand-authored characters (25) | User-defined via GUI | User-defined roles | **NVIDIA Nemotron-Personas-Korea** (7M, KOSIS-census-grounded, narrative + occupation + region + age + income + political-lean) |
| **State / memory** | Stateless within a thread | **Memory stream + reflection + planning** | Modular: memory, planning, tool-use | Conversation state | **Stateless** — one prompt → one JSON; no memory across personas or rounds |
| **Input** | Design spec (rules + seed personas) | World map + character bios | GUI-built world + agents | Natural-language task description | **Korean news article URL** → trafilatura body → LLM brief (행위자 · 조치 · 규모 · 대상 · 시점 · 범위 + key quotes) → **verbatim quote/number guard** |
| **Default LLM** | GPT-3 | GPT-3.5 / GPT-4 | Configurable (paper used GPT-3.5/4) | Configurable | **Qwen3 8B Q4_K_M** via Ollama (5.2 GB, runs on a laptop, $0/run) |
| **Cost (typical run)** | API $$ | Smallville: weeks of GPT-4 ≈ thousands of USD ([Nature coverage](https://www.nature.com/articles/d41586-023-02818-9)) | API $$ | API $$ | **Free** (local). 100 agents in ~14 min on a 16-core CPU + a single 8 GB GPU |
| **Output unit** | Forum posts/replies | Day-by-day agent actions, multi-turn dialogues | Task completion logs | Solved-task transcripts, generated code | `{sentiment, intensity 0–100, reasoning ≤ 2 sentences}` JSON × N |
| **Headline product** | Prototype forum mockup | Interactive "AI village" demo | Eval scores, capability traces | Solved-task output | **Korea map + emoji-avatar wall + demographic bars + 1200×630 social card PNG**, plus per-persona JSON |
| **Auditability of factual claims** | None beyond the LLM | None beyond the LLM | None beyond the LLM | None beyond the LLM | **Verbatim guard rejects any number or quoted phrase that is not a substring of the source article** (after whitespace normalisation) — failures are surfaced on the dashboard, not silently dropped |
| **Locale** | English | English (Smallville is American-suburban) | English | English | Korean primary; locale interface (`koreasim/locales/`) — KR (real, Nemotron-Personas-Korea) + US (Census-inspired stub). New locale ≈ one ~150-LOC file + prompt translation |
| **Currently maintained** | Research artifact (UIST '22) | Research artifact (UIST '23, [code](https://github.com/joonspk-research/generative_agents)) | Research artifact (arXiv 2023) | **Maintenance mode** — superseded by [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/) | Active (2026) |

---

## Per-system breakdown

### 1. Social Simulacra (Park et al., UIST '22)

> *"Creating populated prototypes for social computing systems"* — uses GPT-3 prompt-chains to generate forum members + their posts/replies, so designers can preview how a community-design proposal would behave before building it.

**What it does well.** First demonstration that LLM-generated populations can be *useful design artifacts*, not just curiosities — evaluators couldn't reliably distinguish simulated forum content from real community behavior. The "what if a moderator intervenes here?" loop is the contribution.

**Why it isn't KoreaSim's job.** Social Simulacra outputs *threaded text* (posts and replies). KoreaSim outputs *demographic-segmented opinion distributions* on a single stimulus, with the demographics fixed *a priori* by census data rather than *generated by the LLM from seed personas*. Different output shape, different grounding, different downstream consumer (designer vs analyst).

### 2. Generative Agents — "Smallville" (Park et al., UIST '23)

> *"Interactive simulacra of human behavior"* — 25 GPT-driven characters with **memory streams + reflection + planning** lived in a 2D town for 2 simulated days, hosted parties, formed friendships, recovered from bugs naturally.

**What it does well.** The architectural contribution — memory → reflection → planning loops that produce *believable* multi-day behavior — is the field-defining result. If you want characters that *remember* things and *change* over time, this is the reference design. Code is open ([joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents)).

**Why it isn't KoreaSim's job.**

- **Scale.** Smallville is N=25 hand-authored characters; KoreaSim runs N=100–500 stratified-sampled census-grounded personas.
- **Cost shape.** Smallville's two-day run is on the order of *thousands of GPT-4 USD*. KoreaSim's 200-agent run on Qwen3 8B Q4 is **free** and finishes in ~14 minutes per 100 agents on a laptop GPU.
- **Goal.** Smallville asks *"can agents act like people over time?"* KoreaSim asks *"what does a demographically representative slice of Korea say about this article right now?"* Multi-day continuity vs single-stimulus fan-out are different deliverables.
- **Auditability.** Smallville has no input pipeline; the world is fictional. KoreaSim's URL→brief→verbatim-guard pipeline exists specifically because the input is a real news article and the dashboard has to be traceable back to the source.

If you need a long-running believable village, use Generative Agents. If you need a one-shot poll-shaped read on a real news article, KoreaSim is closer.

### 3. AgentSims (Lin et al., arXiv 2023)

> *"An open-source sandbox for large language model evaluation"* — GUI for building maps + agents, plug-in modules for memory/planning/tool-use, designed so behavioral economists and social psychologists can drop in tasks without writing infra code.

**What it does well.** The **evaluation-first framing** — "I want to test whether memory module X helps capability Y on task Z" — is genuinely orthogonal to most agent demos. The GUI lowers the barrier for non-engineers. If you're benchmarking modules, AgentSims is the right shape.

**Why it isn't KoreaSim's job.** AgentSims is *infrastructure for evaluation*; KoreaSim is *a product for analysts*. AgentSims gives you the dials (memory module, planning module, etc.); KoreaSim gives you a fixed pipeline tuned for one job (Korean news → demographic opinion fan-out) with the dials hidden behind a CLI flag. Different target user (researcher running benchmarks vs analyst running scenarios).

### 4. Microsoft AutoGen

> *"Enabling next-gen LLM applications via multi-agent conversation"* — multiple LLM agents exchange messages, delegate, and execute code to solve a task. Strong code-generation and human-in-the-loop story.

**What it does well.** Task decomposition where *the answer doesn't exist yet and has to be constructed by multi-agent dialogue* — code review, problem-solving, document-drafting pipelines. Industrial-grade. (Currently in maintenance mode, succeeded by [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/), which adds workflows + state management.)

**Why it isn't KoreaSim's job.** AutoGen's mental model is *cooperating agents converging on an answer*. KoreaSim's mental model is *N independent agents each producing their own opinion*, where the *distribution itself is the answer*. There is no convergence step in KoreaSim — disagreement is the signal, not noise.

---

## Where KoreaSim sits

The novelty isn't a new agent architecture (we don't claim one). It's a **vertical pipeline** that the four systems above don't cover:

```
real Korean news URL
   │  trafilatura
   ▼
clean article body
   │  Qwen3 8B + structured-brief prompt
   ▼
{actor, action, magnitude, target, time, scope, key_numbers, quotes}
   │  verbatim guard: every number / quoted phrase must appear in the source body
   ▼  (failures retried once, then surfaced on dashboard)
verified brief
   │  asyncio.gather × N personas, stratified-sampled from Nemotron-Personas-Korea
   ▼
N × {sentiment, intensity, reasoning} JSON
   │  aggregate by region · age · occupation · income · political_lean
   ▼
Korea bubble map · emoji wall · demographic bars · 1200×630 social card · summary JSON · raw JSON
```

Three claims this pipeline lets us defend that the four systems above can't:

1. **The persona dataset is real, not generated.** Region / age / occupation / political-lean distributions come from KOSIS census via Nemotron-Personas-Korea. We are not asking the LLM to invent the population — we are sampling it. ([dataset card](https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea))
2. **The stimulus is a real news article, and the brief is grounded.** No number on the dashboard appears unless that exact substring appears in the source article body. Verbatim-guard failures are visible, not hidden. The dashboard's source-attribution box exists for this reason.
3. **The cost shape allows iteration.** Running a 200-persona simulation against a new article costs ~$0 and ~30 minutes. That changes what kinds of questions an analyst is willing to ask. (Smallville's compute cost is the dominant reason no one else has run it 100 times on different scenarios.)

---

## What KoreaSim is *not*

Listing this here so HN/Reddit comments don't have to extract it from the README:

- **Not a poll.** LLM priors over what a demographic *might* say ≠ asking real people. Calibration vs KSOI / Gallup Korea is a roadmap item, not a current claim.
- **Not multi-turn.** Personas don't argue, don't update on each other's reasoning, and don't accumulate memory across runs. Persona ↔ persona dialogue is a roadmap item; today's product is one-round fan-out.
- **Not a planning agent.** No tool use, no memory stream, no reflection. Each persona sees `system prompt + brief` and emits one JSON.
- **Not a believability benchmark.** Per-persona reasoning is short (≤ 2 sentences) and structured. If you want long, naturalistic dialogue, use Generative Agents.
- **Not Korea-only by architecture.** The persona data and prompts are Korean, but the pipeline is locale-agnostic — see [`docs/LOCALES.md`](LOCALES.md). The US locale stub is intentionally minimal so the *interface* is the demonstration, not US-quality coverage.

---

## Decision guide

| If you want… | Use |
|---|---|
| Believable multi-day agent lives, dialogue, memory | **Generative Agents** |
| Forum-shaped community-design prototyping | **Social Simulacra** |
| To benchmark LLM capabilities on agent tasks | **AgentSims** |
| Multi-agent task-solving / code-gen / dialogue convergence | **AutoGen** / Microsoft Agent Framework |
| *"What does a demographically representative slice of Korea say about this news article, locally, free, in 15 minutes?"* | **KoreaSim** |

---

## References

- Park, J. S., Popowski, L., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2022). *Social Simulacra: Creating Populated Prototypes for Social Computing Systems*. UIST '22. [arXiv:2208.04024](https://arxiv.org/abs/2208.04024)
- Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). *Generative Agents: Interactive Simulacra of Human Behavior*. UIST '23. [arXiv:2304.03442](https://arxiv.org/abs/2304.03442) · [code](https://github.com/joonspk-research/generative_agents)
- Lin, J., Zhao, H., Zhang, A., Wu, Y., Ping, H., & Chen, Q. (2023). *AgentSims: An Open-Source Sandbox for Large Language Model Evaluation*. [arXiv:2308.04026](https://arxiv.org/abs/2308.04026)
- Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., Jiang, L., Zhang, X., Zhang, S., Liu, J., Awadallah, A. H., White, R. W., Burger, D., & Wang, C. (2023). *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation*. [arXiv:2308.08155](https://arxiv.org/abs/2308.08155) · [GitHub](https://github.com/microsoft/autogen)
- NVIDIA. (2026). *Nemotron-Personas-Korea*. [HuggingFace dataset](https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea)
