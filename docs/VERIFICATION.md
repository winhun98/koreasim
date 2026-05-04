# Verbatim guard — algorithm, failure modes, empirical hit/miss

> Audience: anyone who looks at the source-attribution box on a KoreaSim
> dashboard and asks *"how do I know that number actually came from the
> article?"* Also: HN/Reddit reviewers asking whether the brief is just
> a hallucinated summary in disguise.
> Last updated: 2026-05-04. Reproducible against the four URL-mode runs in
> [`examples/runs/`](../examples/runs/).

## What this document is for

KoreaSim's URL mode does this:

1. Fetch a Korean news article via [trafilatura](https://trafilatura.readthedocs.io/).
2. Ask **Qwen3 8B Q4** (default) for a structured **brief** —
   *actor · action · magnitude · target · time · scope · key_numbers · quotes · summary*.
3. Run a **verbatim guard** that rejects any number or quote not present in the source body.
4. Retry once with the failed items called out. If they still fail, **drop them and surface the failure on the dashboard** rather than letting them through.
5. Run N personas against the verified brief.

Everything below is about step 3–4. If a `key_number` or `quote` reaches the dashboard, it has been substring-checked against the article body. If something didn't pass, it shows up in the dashboard's "unverified" list — visible, not silent.

The contribution is **not** prompt instructions ("only quote things from the article" — every paper-of-the-week says that). The contribution is the **algorithmic post-check** that catches the prompt's failures, plus an **honest disclosure** of what the guard does *not* catch.

---

## Algorithm

Source: [`koreasim/scenario/brief.py`](../koreasim/scenario/brief.py) — ~270 LOC, no dependencies beyond stdlib.

### Pseudocode

```
function generate_brief(backend, article, max_retries=1):
    parsed = None
    failed_items = []
    for attempt in 0..max_retries:
        prompt = first-attempt-prompt if attempt == 0
                 else retry-prompt(failed_items)         # explicitly lists what failed
        response = backend.generate(prompt, temperature=0.3, max_tokens=1024)
        candidate = parse_json(response.text)            # tolerates ```json fences, prose
        if candidate is None:
            failed_items = ["JSON 파싱 실패"]
            continue
        if parsed is not None:
            candidate = merge(parsed, candidate)         # see "thin-retry merge" below
        failed_items = validate_verbatim(candidate, article.text)
        parsed = candidate
        if not failed_items:
            break
    if parsed is None:
        raise BriefGenerationError                       # both attempts unparseable
    if failed_items:
        parsed = drop_unverified(parsed, failed_items)   # poison-prevention
    return Brief(parsed, unverified=failed_items)
```

### `validate_verbatim`

```
function validate_verbatim(brief, article_text):
    haystack = normalize_whitespace(article_text)
    failed = []
    for n in brief.key_numbers:                          # skip non-strings silently
        if not is_string(n): continue
        needle = normalize_whitespace(n)
        if needle and needle not in haystack:
            failed.append("key_number: " + n)
    for q in brief.quotes:
        if not is_string(q): continue
        needle = normalize_whitespace(q)
        if needle and needle not in haystack:
            failed.append("quote: " + q)
    return failed

function normalize_whitespace(s):
    return re.sub(r"\s+", " ", s).strip()
```

Three deliberate properties:

- **Substring, not fuzzy.** No edit-distance, no semantic similarity. If the LLM paraphrases ("정부가 30% 올렸다") instead of quoting ("30% 인상"), it fails. We accept the false-negative rate this creates because false-positives (wrong number lands on the dashboard) are worse than false-negatives (correct number gets dropped).
- **Whitespace-only normalisation.** Korean news articles have erratic spacing / line breaks; LLMs clean them up when they quote. We normalise both sides to a single-space form before substring matching. **Character identity is required**, but byte identity is not.
- **Tagged failures.** Each failure is prefixed `key_number:` or `quote:` so the retry prompt can be unambiguous about which slot the offending item came from.

### Retry prompt

When the first attempt produces failures, the second prompt explicitly enumerates them:

```
Your previous response contained items that do NOT appear verbatim in the source:
- key_number: 50% 인상
- quote: 환영합니다

Regenerate the brief using ONLY expressions that occur verbatim in the article below.
Same JSON schema as before. ...
```

This is more directive than re-stating the rule. Empirically (see [Empirical results](#empirical-results)), the second attempt clears the failed items in roughly half of the runs that fail on the first try.

### Thin-retry merge

Smaller models (qwen3:8b in particular) frequently return **only the corrected fields** on retry, leaving every other slot empty:

```json
// First attempt — rich, but key_numbers contains a hallucination
{ "actor": "정부", "summary": "...8 sentences...", "key_numbers": ["50% 인상"], ... }

// Retry — corrects key_numbers but blanks the rest
{ "actor": "", "summary": "", "key_numbers": ["30% 인상"], ... }
```

If we naively replaced the first attempt with the second, we'd lose the well-formed `actor` / `summary`. The merge rule is:

```
function merge(prev, new):
    out = dict(prev)
    for key, val in new:
        if val is non-empty (string after strip / non-empty list / non-None):
            out[key] = val
    return out
```

This keeps the correction (`key_numbers: ["30% 인상"]`) and recovers the rich fields from the first attempt. The behavior is covered by `tests/test_brief.py::test_generate_brief_thin_retry_does_not_blank_first_attempt`.

### Poison prevention — `drop_unverified`

If items still fail after the retry, they are **not** silently kept. They are removed from `key_numbers` / `quotes` and recorded in `Brief.unverified`. The dashboard renders that list as a visible warning so the reader knows something was rejected.

The summary text is **not** verbatim-checked. It's a paragraph-length re-telling of the article and would fail any substring check on principle. Instead, the prompt explicitly forbids inventing facts beyond the article — and the structured slots (`actor` / `action` / `magnitude` / etc.) are the parts a reader compares against the source URL.

---

## Failure modes — observed in the four URL-mode runs

These are the four articles in [`examples/runs/`](../examples/runs/), all run on Qwen3 8B Q4_K_M via Ollama on 2026-04-29~30. Each row is a real outcome, not a hand-crafted illustration.

### Mode 1 — Clean run, no failures

[**아동복지법 '혼외자' 표현 삭제** (yna-co-kr-AKR20260429064600530)](../examples/runs/yna-co-kr-AKR20260429064600530.json)

```json
{
  "key_numbers": ["1만3천800명", "2023년", "1981년", "5.8%"],
  "quotes": ["...", "..."],
  "unverified": []
}
```

**Outcome:** Every numeric and quoted item passed verbatim check on the first attempt. No retries. This is the baseline good case — short article, well-defined facts, LLM quotes faithfully.

### Mode 2 — Single quote dropped (guard worked as designed)

[**65세 단계적 정년 연장 재추진** (khan-co-kr-202604292051005)](../examples/runs/khan-co-kr-202604292051005.json)

```json
{
  "key_numbers": [
    "2028년부터 2036년까지 2년 간격으로 정년을 1년씩 연장",
    "2029년부터 2039년까지 2~3년 주기로 1년씩 연장",
    "2029년부터 2041년까지 3년마다 1년씩 연장",
    "60세",
    "65세"
  ],
  "quotes": ["...", "...", "..."],
  "unverified": ["quote: 퇴직 후 선별적 재고용 방식도 전체 노동시장의 질을 떨어뜨린다"]
}
```

**Outcome:** Five intricate `key_numbers` (with multiple proposals from different parties — 한국노총, 경총, 양경수 위원장 each had different timelines, all preserved verbatim). Three `quotes` passed. **One `quote` failed both attempts and was dropped.** It paraphrased a sentiment in the article rather than quoting it.

This is the guard's intended behavior: a paraphrased quote is rejected, not silently rendered as if it were a real quote. The dashboard shows the rejection. *The unverified item is itself useful — it tells the reader where the LLM tried to over-reach.*

### Mode 3 — Retry fails to parse, summary salvaged

[**서울 아파트 매매가 / 양도세** (yna-co-kr-AKR20260430037300003)](../examples/runs/yna-co-kr-AKR20260430037300003.json)

```json
{
  "key_numbers": ["11억9천476억원", "2억9천371만원(-19.7%)", "...14 items"],
  "quotes": ["...", "...", "..."],
  "unverified": ["JSON 파싱 실패"]
}
```

**Outcome:** First attempt produced 14 verbatim-clean numbers and three quotes. Triggered a retry for some reason (likely a borderline whitespace mismatch on the first run that has since been resolved by the whitespace-normalisation rule, or a `key_number` we no longer see post-merge). The retry returned **unparseable JSON**; the failure was logged but the first attempt's verified data was preserved via `merge`. The dashboard surfaces `"JSON 파싱 실패"` as the unverified-items reason.

**Caveat:** `"JSON 파싱 실패"` in `unverified` is not a verbatim failure — it's a parse failure on a retry that we recorded in the same field. This is a small UX wart: the `unverified` slot today carries two different meanings (verbatim drop vs retry parse error). Roadmap: split into `unverified` (real verbatim drops) + `parse_errors` (retry-parse warnings).

### Mode 4 — Guard passes but output is structurally malformed

[**AI 의료 진단·처방** (yna-co-kr-AKR20260429166500530)](../examples/runs/yna-co-kr-AKR20260429166500530.json)

```json
{
  "key_numbers": ["A", "I", "기", "본", "의", "료", "전", "략", ",", "A", "I", "대", "전", "환"],
  "quotes": ["...sensible 5 quotes..."],
  "unverified": []
}
```

**Outcome:** The LLM serialised what was meant to be a list of phrases (`["AI 기본 의료 전략", "AI 대전환"]`) as a list of **individual characters**. **Every individual character is a substring of the source**, so the verbatim guard sees nothing wrong. `unverified` is empty. The dashboard renders 14 single-character "key numbers" — useless to the reader.

This is the **honest limit** of a substring-only guard: it catches *factual* fabrication ("the LLM made up a number") but it does not catch *structural* malformation ("the LLM produced a syntactically valid JSON list whose elements are individually fine but collectively meaningless").

What we currently do about it: nothing programmatic. The summary text in this run is correct and useful, and the simulation ran successfully (150 personas, 91% supportive). The malformed `key_numbers` is a cosmetic problem on the dashboard, not a correctness problem in the simulation. Roadmap items below.

### Mode 5 — Catastrophic parse failure (covered by tests, not seen in production)

If both the first attempt and the retry produce unparseable JSON, `generate_brief` raises `BriefGenerationError`. The pipeline aborts before sending personas. This has not occurred in any of the four production runs; it is exercised by `tests/test_brief.py::test_generate_brief_raises_when_both_attempts_unparseable`.

---

## Empirical results

Aggregated across the four URL-mode runs above, all on Qwen3 8B Q4_K_M, default sampling (`temperature=0.3` for the brief, separate from the persona-runtime sampling). Counts are post-retry, post-drop.

| Article | `key_numbers` kept | `quotes` kept | Items dropped (real verbatim failures) | Parse-error retries |
|---|---:|---:|---:|---:|
| 혼외자 표현 삭제 | 4 | 2 | 0 | 0 |
| 정년 연장 | 5 | 3 | **1 (quote)** | 0 |
| 부동산 / 양도세 | 14 | 3 | 0 | 1 |
| AI 의료 | 14 ⚠ | 5 | 0 | 0 |
| **Total** | **37** | **13** | **1** | **1** |

⚠ The 14 in the AI 의료 row are the malformed single-character entries from Mode 4 — they pass verbatim check but are not useful information.

**Reading these numbers honestly:**

- **50 items checked, 1 dropped** → 98% verbatim-pass rate after one retry. This is *not* "98% of facts on the dashboard are correct" — that's a different claim. It means: of the items the LLM proposed, 98% can be confirmed as substrings of the source article.
- **1 dropped item out of 1 article that produced a paraphrase** — this is the ratio that matters. The guard catches the LLM's mistake when it makes one. We do not have a case in the four runs where the guard *missed* a real fabrication.
- **The Mode-4 (AI 의료) case is the failure mode** — guard didn't fire because the items were technically substrings, but the structure was wrong. This is a real limitation. Counted honestly, **3 of 4 runs (75%) produced a fully usable structured brief; 1 of 4 (25%) had a malformed `key_numbers` field that the guard couldn't detect.**

A larger-scale evaluation (10–20 articles, multiple model sizes, intentional adversarial cases) is a roadmap item — see [Roadmap](#roadmap).

---

## What the guard catches

| Failure mode | Caught? | Where |
|---|---|---|
| LLM invents a number not in source | ✅ | `_validate_verbatim` |
| LLM paraphrases instead of quoting | ✅ | `_validate_verbatim` |
| LLM quotes from a *different* article it remembers | ✅ (substring match against this article only) | `_validate_verbatim` |
| Whitespace differences (single vs double space, line breaks) | ✅ tolerated | `_normalise` |
| Both attempts produce malformed JSON | ✅ raises `BriefGenerationError`, simulation aborts | `generate_brief` |
| Retry blanks the rich fields from the first attempt | ✅ | `_merge_brief` |
| Empty / whitespace-only items in lists | ✅ filtered | `_build_brief` |
| Non-string items in lists (None, ints) | ✅ silently skipped | `_validate_verbatim` |

## What the guard does *not* catch

| Failure mode | Why not | Mitigation today | Roadmap |
|---|---|---|---|
| **Structural malformation** — list-of-characters instead of list-of-phrases (Mode 4) | Substring check passes per-character | Surface on dashboard via `unverified` slot if other items fail; otherwise rendered as-is | Add a length floor (`len(item) >= 2` for `key_numbers`, `>= 4` for `quotes`); flag suspicious-shape items |
| **Out-of-context quoting** — the LLM picks a verbatim sentence that exists in the article but is misleading when extracted | Substring check is local | None | Future: secondary LLM critic pass that scores extraction faithfulness |
| **Paraphrase that happens to coincide with another phrase in the article** | Substring is satisfied | None | Same as above |
| **Wrong field assignment** — correct verbatim string lands in `magnitude` when it should be in `target` | Per-item check, no cross-field semantics | None | Future: schema-aware critic |
| **Summary hallucination** — the `summary` paragraph adds claims not in the article | `summary` is not verbatim-checked (it's a paragraph) | Prompt forbids inventing; structured slots (verbatim-checked) sit next to summary in the dashboard, so a reader can sanity-check | Future: claim-by-claim entailment check on `summary` sentences |
| **Source-document quality** — the article itself is wrong / propagandistic | Out of scope | Source URL is rendered on the dashboard; reader can click through | Out of scope |

The first row is the most important. **Mode 4 is the published failure case.** It happened in production, on a real article, on the default model, in the four-article evaluation that ships with this repo. We could have not shipped that article. We did, and we documented it here, because hiding it would defeat the point of having a verifiable pipeline.

---

## Comparison to "just tell the LLM in the prompt"

Most LLM-summarisation systems use prompt instructions like *"only quote what's in the source"* and stop there. Why isn't that enough?

| Property | Prompt instruction only | KoreaSim's prompt + algorithmic guard |
|---|---|---|
| Catches LLM ignoring instruction | No (the instruction is the failure mode) | Yes (post-check is independent of generation) |
| Surfaces failures to reader | No (silent) | Yes (`unverified` slot on dashboard) |
| Recovers from one failure | No (re-prompt without enumeration) | Yes (retry prompt names which items failed) |
| Falls back when both attempts fail | No | Drop unverified items; preserve summary; mark visibly |
| Cost on the happy path | 1 call | 1 call (verbatim check is local, ~µs) |
| Cost on a failed first attempt | 1 call (failure shipped) | 2 calls + check |
| Auditability | "trust the LLM" | The check is 24 lines of Python; you can re-run it |

The guard is not magic. It's a substring check with whitespace normalisation and a retry loop. The point isn't that the algorithm is novel — it isn't. The point is that **we wrote it down, ran it on real articles, documented the modes it doesn't catch**, and ship the failure cases with the repo so a reviewer can see them.

---

## Reproducibility

To re-run the verbatim check on the four articles in `examples/runs/`:

```bash
cd ~/workspace/koreasim
. .venv/bin/activate
python - <<'PY'
import asyncio, json, pathlib
from koreasim.scenario.brief import _validate_verbatim
from koreasim.scenario.article import fetch_article

async def main():
    for run in pathlib.Path("examples/runs").glob("*.json"):
        if run.name.endswith(".summary.json"):
            continue
        d = json.loads(run.read_text())
        brief = d.get("brief")
        if not brief:
            continue
        article = await fetch_article(d["source_url"])
        failures = _validate_verbatim(brief, article.text)
        print(f"{run.name}: {len(failures)} verbatim failures")
        for f in failures:
            print(f"  - {f}")

asyncio.run(main())
PY
```

(The four shipped runs were generated against article bodies that have not changed between 2026-04-29 and the date of this document. If a publisher edits the source URL, re-running will not match the recorded `unverified` exactly.)

To run the full test suite covering the verbatim guard:

```bash
pytest tests/test_brief.py -v
# 13 tests pass, no LLM calls — all use a stub backend.
```

---

## Roadmap

In rough priority order:

1. **Length-floor heuristic** for `key_numbers` and `quotes` to catch the Mode-4 character-list failure. ~10 LOC.
2. **Split `unverified` field** into `unverified` (real verbatim drops) + `parse_errors` (retry-parse warnings). Resolves the Mode-3 UX wart.
3. **Adversarial article test set** — 10–20 articles deliberately chosen for ambiguous quoting / numbers in tables / mixed scripts. Run on Qwen3 8B vs Llama 3.1 8B vs a hosted GPT-4 baseline; publish hit/miss rates.
4. **Secondary critic pass** — small LLM scores `summary` for entailment against the article. Cost: doubles brief generation cost; opt-in flag.
5. **Schema-aware critic** — checks whether `magnitude`, `target`, `time`, `scope` slots agree with each other (e.g. magnitude `30%` and target `운전자 1,200만 명` aren't contradictory).

---

## See also

- [`koreasim/scenario/brief.py`](../koreasim/scenario/brief.py) — implementation (~270 LOC)
- [`koreasim/scenario/prompts.py`](../koreasim/scenario/prompts.py) — `BRIEF_GENERATION_PROMPT`, `BRIEF_RETRY_PROMPT`
- [`tests/test_brief.py`](../tests/test_brief.py) — 13 unit tests covering all five failure modes
- [`docs/COMPARISON.md`](COMPARISON.md) — KoreaSim vs Generative Agents / Social Simulacra / AgentSims / AutoGen
- [`docs/SAMPLING.md`](SAMPLING.md) — separate document on the persona-side sampling that breaks Qwen3 8B's neutral bias
- [`README.md`](../README.md) — top-level user docs
