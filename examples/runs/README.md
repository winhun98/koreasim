# Live runs — Real Korean news (2026-04-29 ~ 2026-04-30)

Four real Korean news articles simulated with `koreasim run --url <URL>`.
**🌐 Open the live dashboards directly via GitHub Pages** (links below) — no clone needed.

| Slug | Source article | Live dashboard | N | Topic |
|---|---|---|---:|---|
| `khan-co-kr-202604292051005` | [khan.co.kr](https://www.khan.co.kr/article/202604292051005) | [🌐 dashboard](https://winhun98.github.io/koreasim/examples/runs/khan-co-kr-202604292051005.html) | 150 | 65세 단계적 정년 연장 재추진 |
| `yna-co-kr-AKR20260430037300003` | [yna.co.kr](https://www.yna.co.kr/view/AKR20260430037300003) | [🌐 dashboard](https://winhun98.github.io/koreasim/examples/runs/yna-co-kr-AKR20260430037300003.html) | 200 | 1분기 서울 아파트 전용 84㎡ 매매가 작년보다 20% 하락 |
| `yna-co-kr-AKR20260429166500530` | [yna.co.kr](https://www.yna.co.kr/view/AKR20260429166500530) | [🌐 dashboard](https://winhun98.github.io/koreasim/examples/runs/yna-co-kr-AKR20260429166500530.html) | 150 | AI로 진단·처방 보조…취약지 의료 공백 해소 |
| `yna-co-kr-AKR20260429064600530` | [yna.co.kr](https://www.yna.co.kr/view/AKR20260429064600530) | [🌐 dashboard](https://winhun98.github.io/koreasim/examples/runs/yna-co-kr-AKR20260429064600530.html) | 150 | 아동복지법서 '혼외자' 표현 삭제 |

Each slug has 4 files:

- `<slug>.html` — interactive dashboard (Korea map · emoji wall · bars · brief box)
- `<slug>.card.png` — 1200×630 social card
- `<slug>.json` — full reactions + persona index + brief
- `<slug>.summary.json` — aggregate stats

## Reproducing

```bash
# Same Ollama setup the README assumes
ollama pull qwen3:8b

# Article URL → fetch → brief → simulate → save
koreasim run --url "<URL from table above>" --n 150 --model qwen3-8b --out examples/runs
```

Sampling is deterministic on the persona side (seed=42 default). LLM outputs
vary slightly per re-run — the pinned files in this folder were generated on
2026-04-30 with `qwen3:8b` Q4_K_M via Ollama.

## Brief verification

Three of four briefs passed the verbatim guard (`key_numbers` and `quotes`
exactly present in the source) on the first or second LLM attempt:

- `AKR20260429166500530` (AI 의료) — clean
- `AKR20260429064600530` (혼외자) — clean
- `AKR20260430037300003` (부동산) — 1 unverified item (`JSON 파싱 실패` on 1st attempt, retry succeeded)
- `khan-co-kr-202604292051005` (정년 연장) — 1 quote dropped (verbatim mismatch on retry)

The first khan URL we tried (`/article/202604292229005`) failed to extract
sufficient body text (1,214 chars) and was rejected by the brief generator
after both attempts returned unparseable JSON. We retried with the longer
related article above. This is the expected behaviour for short or
paywalled sources — see [README.md](../../README.md#-quickstart).
