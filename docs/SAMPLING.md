# Sampling & prompt strategy — empirical log

**TL;DR.** Out-of-the-box Qwen3 8B answers KoreaSim scenarios with **64% mean
neutral** — the model's RLHF training pushes it toward "balanced" responses
when uncertain. Three layers (sampling tweak + stake-elicitation prompt +
rejection sampling) drop that to **51% mean neutral**, with avg intensity
41 → 52 and empty-response rate to 0%, while keeping legitimate neutrals
(e.g. non-수도권 personas on 수도권-housing scenarios) intact.

## Setup

- Model: `qwen3:8b` (Q4_K_M) via Ollama at :11434
- Persona sample: 100 stratified personas, seed=42 (same set across all runs)
- 5 scenarios: `pension_age`, `housing_price`, `kospi_crash`, `minimum_wage`, `ai_replacement`
- Each cell = N=100 reactions (500 reactions per experiment configuration)

## Three configurations

| Config | Sampling | Prompt | Rejection sampling |
|---|---|---|---|
| **baseline** | T=0.7, top_p=0.9, no min_p | basic ("위 시나리오가 본인의 일상에 어떤 영향") | retry on empty (3×, no fallback) |
| **v2** | T=0.9, top_p=0.95, **min_p=0.05** | **stake elicitation + neutral usage condition** | retry on empty (3×, no fallback) |
| **v3** | T=0.9, top_p=0.95, **min_p=0.03** | stake elicitation + neutral usage condition | **fallback prompt on attempt 3** |

## Aggregate results (mean over 5 scenarios × N=100)

| Metric | baseline | v2 | v3 | v3 vs baseline |
|---|---:|---:|---:|---:|
| Mean neutral % | 64.0 | 53.0 | **50.6** | **−13.4 pp** |
| Mean avg intensity | 41.5 | 53.9 | **51.8** | **+10.3** |
| Total empty (/500) | 3 | 68 | **0** | **−3** |
| Total truncated (/500) | 63 | 109 | **54** | −9 |

## Per-scenario neutral % (baseline → v3)

| Scenario | baseline | v3 | Δ |
|---|---:|---:|---:|
| pension_age | 60 | 45 | **−15** |
| housing_price | 63 | 64 | +1 |
| kospi_crash | 57 | 43 | **−14** |
| minimum_wage | 67 | 52 | **−15** |
| ai_replacement | 73 | 49 | **−24** |

`housing_price` is the exception — it stays flat in aggregate. But split by region:

| Region group | baseline neutral | v3 neutral | Δ |
|---|---:|---:|---:|
| 수도권 (서울/경기/인천) | 24% | **10%** | **−14 pp** |
| 비수도권 | 87% | **98%** | +11 pp |

The new prompt didn't fail here — it correctly identified that **non-수도권
personas have no direct stake** in 수도권 housing prices, so they should
*be* neutral. The aggregate stays flat because most personas in a stratified
Korean sample are non-수도권. Within 수도권, opinions form sharply.

## Side effect: supportive opinions emerged

| Scenario | baseline supportive % | v3 supportive % |
|---|---:|---:|
| minimum_wage | 12 | **19** |
| ai_replacement | 17 | **30** |

These weren't created from thin air — they were latent in the persona
distribution and got suppressed by neutral bias. Demographic breakdown:

- **minimum_wage supportive (19/100)**: 12 are 20–30대, 4 전업주부 (어린 자녀 가구의 가계 보탬), 3 영업사원, 2 대학생
- **ai_replacement supportive (30/100)**: 4 자영업 사장, 3 each of 개발자·교사·대학생, 2 each of 회계사·변호사 — broad professional/student coalition framing automation as efficiency

## What each layer contributes

### Layer 1: sampling

`temperature=0.7 → 0.9` and `min_p=0 → 0.03~0.05`. min_p is the lever — it
clips low-probability tokens *relative to the top token*. The "neutral"
token is conventionally low-confidence at the JSON sentiment slot, but it's
in the safe-band (mid-probability) that other clipping methods (top_p, top_k)
preserve. min_p removes that safe band.

### Layer 2: stake-elicitation prompt

The original prompt asked "본인의 일상에 어떤 영향을 줄지" — too easy to
answer with "큰 영향 없음 → neutral". The new prompt does two things:

1. Specifies the dimensions to anchor on: 나이·지역·직업·소득·정치성향
2. **Forbids escape neutrals**: "영향이 있는데 의견이 양가적이면 더 강하게
   느끼는 쪽 선택. 회피용 중립 금지."

This makes the model commit when there's genuine personal stake. If there's
no stake (non-수도권 + 수도권 housing), neutral remains correct.

### Layer 3: rejection sampling

The harder prompt + aggressive sampling combo causes 14% of personas to
return empty content (Qwen3 enters thinking mode despite `/no_think` and
exhausts max_tokens). Empty cases concentrate in **전업주부·학생·농어민**
— personas with weakest direct stake on the test scenarios. On attempt 3
(after 2 retries with the full prompt), `_react_one` falls back to a minimal
prompt:

```
본인 신원에 비춰 위 시나리오에 대한 입장을 짧게 답하세요. JSON만 출력:
{ "sentiment": ..., "intensity": ..., "reasoning": "한 문장" }
```

This recovers all 14% as real (mostly neutral) responses. Empty rate drops
to 0%.

## Cost

- **Time**: 30s/scenario (baseline) → 17min/scenario (v3). The stake-elicitation
  prompt produces ~4× longer reasoning, which is most of the cost. 5-scenario
  full run is ~85 minutes on a 16-core CPU + GPU via Ollama.
- **Tokens per persona**: ~150 input + ~150 output baseline → ~300 input + ~600 output v3.
- **No additional API cost** — all local.

## When to override defaults

Cases where you might want to dial v3 settings *back* toward baseline:

- **Inference-budget-bound demos**: drop `min_p` to 0 and `temperature` to 0.7
  to halve generation time. Neutral % will rise but per-scenario direction stays.
- **You want raw model priors**: skip the stake-elicitation prompt — pass a
  custom `prompt_template` to `ScenarioRunner`. Useful for benchmarking the
  model itself rather than KoreaSim's interpretation of it.
- **You're using a base/non-RLHF model** (e.g. DPO-stripped Korean fine-tunes):
  the neutral attractor is much weaker; `min_p=0.01` or 0 is enough.

## Open questions

- Calibration: does the lower-neutral distribution match real polling
  (KSOI, Gallup Korea) better than the baseline's flat 64%? Roadmap item.
- Could DPO on a small set of "neutral when stake exists" rejected pairs
  remove the bias at the model level, removing the need for prompt scaffolding?
- Does the same recipe transfer to other RLHF'd Korean models (EXAONE,
  HyperCLOVA-X)? Untested.

---

**Reproducing**: experiment scripts are in `/tmp/exp_v3.py` (see git history
for the canonical version). Persona seed=42, scenarios listed above. Mean
neutral target **35–50%** (45.5% true rate excluding housing_price's
geographic-stake artifact).
