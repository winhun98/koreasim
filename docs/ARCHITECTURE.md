# KoreaSim Architecture

## Module map

```
koreasim/
├── persona/
│   ├── schema.py       # KoreanPersona, Reaction (dataclasses)
│   ├── sample.py       # KOSIS-inspired offline sample generator
│   └── loader.py       # PersonaLoader (HF / JSONL / sample)
├── llm/
│   ├── backend.py      # LLMConfig, OpenAICompatibleBackend, MockBackend
│   └── models.py       # Preset registry (qwen3-8b, llama3.1-8b, bitnet-2b, ...)
├── scenario/
│   ├── prompts.py      # SCENARIO_TEMPLATES + Korean reaction + brief prompts
│   ├── runner.py       # ScenarioRunner (async parallel) + JSON parser
│   ├── article.py      # URL → trafilatura clean text + disk cache
│   └── brief.py        # LLM-driven brief extraction + verbatim-quote guard
├── analysis/
│   ├── aggregate.py    # aggregate_by(...) + summarize(...)
│   └── compute.py      # receipt_for_run (vs-GPT-4o cost)
├── viz/
│   ├── dashboard.py    # plotly HTML dashboard + Rich text report
│   ├── korea_map.py    # 17 광역시도 choropleth (Plotly Choropleth)
│   ├── people_grid.py  # Emoji-avatar people wall (clickable)
│   └── social_card.py  # 1200×630 OG / X card PNG
└── cli.py              # `koreasim run / demo / list-scenarios / list-models`
```

## Data flow

1. **Load**. `PersonaLoader.from_huggingface(count=N)` streams `nvidia/Nemotron-Personas-Korea`
   and maps each row into a `KoreanPersona` (tolerant of schema drift via `_FIELD_ALIASES`).
   `PersonaLoader.sample(N)` is the offline alternative — it mimics rough KOSIS distributions
   for reproducible CI/demos.

2. **Filter / stratify**. `loader.filter(...)` chains predicate filters (region, age range, etc.).
   `loader.stratified_sample(n, by="region")` rebalances over a key so a small sample stays
   demographically diverse.

2.5. **(URL mode only) Article → brief**. When invoked as `koreasim run --url <URL>`,
   `article.fetch_article(url)` does an `httpx` GET, runs the response through
   `trafilatura.extract`, and caches the cleaned body to `~/.cache/koreasim/articles/`.
   `brief.generate_brief(backend, article)` then calls the LLM once with the
   `BRIEF_GENERATION_PROMPT` (English instructions, Korean output) to extract a
   structured brief (`actor / action / magnitude / target / time / scope / key_numbers /
   quotes / summary`). Items in `key_numbers` and `quotes` are verbatim-checked against
   the source text; failures trigger a single retry, and any items that still fail are
   dropped and recorded in `unverified`. The brief's `summary` is then used as the scenario
   text for step 4 below; `source_url` and the full brief dict are propagated into
   `ScenarioResult` for dashboard rendering.

3. **Prompt**. Each persona renders to a Korean system prompt via `KoreanPersona.to_system_prompt()`.
   The persona's `narrative` field (Gemma-generated Korean back-story from Nemotron-Personas-Korea)
   is the cultural grounding; the structured fields (region/age/occupation) are the statistical grounding.

4. **Generate**. `ScenarioRunner.run(personas, scenario)` launches `asyncio.gather` over all
   personas. Each call is a single `/v1/chat/completions` request. The semaphore in
   `OpenAICompatibleBackend` limits concurrent requests (default `n_parallel=4` — Ollama
   truncates responses under higher contention; raise it for vLLM / hosted endpoints).

5. **Parse**. BitNet 1.58b is small — outputs are sometimes messy. `_parse_reaction()` tries:
   strict JSON → first JSON object substring → keyword heuristic. Always returns a `Reaction`.

6. **Aggregate**. `aggregate_by(result, by="age_bucket")` returns one `AggregateRow` per group
   with sentiment counts, intensity averages, and quotable reasoning samples.

7. **Render**. `build_dashboard(result, path)` produces a single HTML file. `render_text_report`
   produces a Rich-formatted ANSI report for terminals.

## Key design choices

- **One scenario per `run()`**. We trade multi-round depth for parallelism — a single scenario
  fans out into N independent persona reactions. Future versions will add multi-round dialogues.
- **Async over multiprocessing**. `httpx.AsyncClient` + asyncio is enough because the bottleneck
  is the LLM server, not Python. No GIL workarounds needed.
- **Backend-agnostic**. `LLMBackend` is an abstract interface. `OpenAICompatibleBackend` works
  against bitnet.cpp, vLLM, llama.cpp, NIM, OpenAI itself. `MockBackend` makes CI deterministic.
- **Fail-soft parsing**. Tiny models hallucinate JSON syntax. The runner never crashes on a bad
  response — it falls back to keyword sentiment + records `raw_response` for debugging.
- **No magic numbers in prompts**. The Korean reaction prompt asks for a constrained JSON shape
  with explicit category definitions. We do *not* try to coax the model into writing essays.

## Where the "demographic accuracy" comes from

- **Names**: Nemotron-Personas-Korea uses the Korean Supreme Court's actual name distribution
  (~118 family names × ~21K given names).
- **Regions**: 17 광역시도 / 25 자치구 weighted by KOSIS 2020-2026 population data.
- **Occupations**: 2,000+ occupation strings sampled in proportion to regional employment data.
- **Cultural narratives**: 7 persona archetypes (professional / family / sports / arts / travel /
  culinary / concise) generated by Gemma-4-31B in natural Korean.

KoreaSim does *not* re-derive any of this — it consumes the dataset as-is and uses it as the
ground-truth distribution from which we sample agents.

## Things this is NOT

- **Not a poll**. Reactions are a model's *prior* over what someone with this profile *might*
  say. Calibration against KSOI / Gallup Korea is a roadmap item, not a current claim.
- **Not RLHF'd for Korean civic discourse**. BitNet 1.58b-2B is a tiny base model. Reactions
  will be flatter/more generic than a real Korean's lived response.
- **Not deterministic in production**. With temperature > 0, a re-run yields slightly different
  reactions per persona. Use `MockBackend` (or fix `temperature=0`) for reproducibility.
