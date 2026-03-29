# SentimentTree Role 2 Integration Guide

This folder contains Role 2 of the SentimentTree application: the semantic processing layer that sits between raw ingestion and downstream decision, clustering, or UI stages.

There are currently two supported workflows:

1. The original text enrichment pipeline for generic scraped items.
2. The newer event to prediction affinity pipeline for scoring how live events affect prediction market outcomes.

If you are another agent or engineer integrating this stage into adjacent stages, use this document as the contract of record.

## What This Stage Owns

Role 2 is responsible for turning raw text or event objects into structured, semantically useful outputs.

It provides:

- Local embeddings using `BAAI/bge-small-en-v1.5`
- Relevance filtering
- Directional sentiment scoring for contract-centric text analysis
- Named entity and topic tagging
- Persistent vector storage in ChromaDB
- Semantic search over stored enriched items
- Event to prediction candidate filtering with embeddings
- Event to prediction LLM scoring with streamed dictionary outputs

It does not provide:

- Web scraping or upstream event collection
- Final branching, clustering, ranking, or UI presentation
- Market execution or any trading logic

## Repository Layout

Key files:

- `main.py`: CLI entry point
- `pipeline/config.py`: central config defaults
- `pipeline/models.py`: all Pydantic contracts shared across stages
- `pipeline/pipeline.py`: original enrichment pipeline orchestrator
- `pipeline/affinity_pipeline.py`: two-stage event to prediction pipeline
- `pipeline/candidate_filter.py`: Stage 1 embedding filter for event/prediction pairs
- `pipeline/llm_scorer.py`: Stage 2 LLM scoring
- `pipeline/vector_store.py`: ChromaDB persistence and retrieval
- `pipeline/semantic_search.py`: semantic search wrapper
- `events_example.json`: sample event payload
- `polymarket_preds.json`: sample prediction payload
- `tests/test_pipeline_stages.py`: regression coverage for the original pipeline

## Runtime Assumptions

This project was stabilized on Python 3.11 after dependency issues on Python 3.13.

Recommended environment:

- Python `3.11.x`
- Editable install via `pip install -e .`
- CLI command: `sentimentree`

Install flow:

```powershell
cd sentiment-tree
pip install -r requirements.txt
python -m spacy download en_core_web_sm
pip install -e .
```

Environment variables:

- `CLAUDE_API_KEY` or `ANTHROPIC_API_KEY` for Anthropic
- `OPENAI_API_KEY` for OpenAI-compatible providers
- Optional `HF_TOKEN` to avoid Hugging Face download rate limits

The CLI loads `.env` automatically through `python-dotenv`.

## Pipeline A: Generic Text Enrichment

Use this when upstream sends generic scraped text and downstream needs enriched semantic features.

Flow:

```text
RawItem
  -> embedding
  -> relevance filter against a contract question
  -> directional sentiment score
  -> NER and topic tags
  -> optional ChromaDB storage
  -> EnrichedItem
```

Primary orchestrator:

- `pipeline.pipeline.Pipeline`

### Input Contract

`RawItem` from `pipeline/models.py`

```python
{
     "text": str,
     "source": str,
     "timestamp": datetime,
     "url": str,
}
```

### Output Contract

`EnrichedItem` from `pipeline/models.py`

```python
{
     "text": str,
     "source": str,
     "timestamp": datetime,
     "url": str,
     "embedding": list[float],
     "sentiment_score": float,
     "sentiment_confidence": float,
     "topic_tags": list[str],
     "entities": list[str],
     "relevance_score": float,
}
```

### Programmatic Example

```python
from datetime import datetime, timezone

from pipeline.models import RawItem
from pipeline.pipeline import Pipeline

pipe = Pipeline("Will Bitcoin reach $100k by end of 2026?")

item = RawItem(
     text="Bitcoin ETF inflows hit $1B this week.",
     source="news_rss",
     timestamp=datetime.now(timezone.utc),
     url="https://example.com/article",
)

result = pipe.process_single(item)
if result is not None:
     enriched_dict = result.model_dump()
```

### Downstream Handoff Guidance

If another stage consumes the enrichment pipeline output, it should treat `relevance_score`, `sentiment_score`, `sentiment_confidence`, `topic_tags`, and `entities` as the stable handoff fields. The embedding vector is available, but downstream should not assume a different embedding size unless `embedding_model` changes intentionally.

Current embedding model:

- `BAAI/bge-small-en-v1.5`

## Pipeline B: Event to Prediction Affinity

Use this when upstream sends normalized event objects and a prediction market stage provides market contracts. This is the more important integration surface for the current application.

Flow:

```text
Event + Prediction
  -> Stage 1: embedding similarity filter
  -> Stage 2: LLM scoring
  -> streamed dict results and/or JSON output
```

Primary orchestrator:

- `pipeline.affinity_pipeline.AffinityPipeline`

### Input Contracts

`EventSource`

```python
{
     "Source": str,
     "Link": str,
     "Summary": str,
}
```

`Event`

```python
{
     "Title": str,
     "Description": str,
     "Sources": list[EventSource],
     "ID": int,
     "embedding": list[float] | None,
}
```

`Prediction`

```python
{
     "id": str,
     "source": str,
     "question": str,
     "category": str,
     "yes_probability": float,
     "no_probability": float,
     "volume_usd": float,
     "liquidity_usd": float,
     "closes_at": datetime,
     "url": str,
     "embedding": list[float] | None,
}
```

Notes for upstream stages:

- Event IDs should be stable integers.
- If embeddings are already attached, Stage 1 will reuse them.
- Predictions may come in as either a raw list or `{ "predictions": [...] }` through the CLI.

### Stage 1 Output Contract

`AffinityPipeline.stage1(...)` returns:

```python
list[tuple[Event, Prediction, float]]
```

Each tuple is:

- `event`
- `prediction`
- `embedding_similarity`

This is the cheapest integration point if a downstream stage wants to do custom scoring instead of using the built-in LLM scorer.

### Stage 2 Output Contract

`AffinityPipeline.stream(...)` yields dictionaries one at a time.

Each dict has this shape:

```python
{
     "event_id": int,
     "prediction_id": str,
     "event_title": str,
     "prediction_question": str,
     "embedding_similarity": float,
     "direction": float,
     "magnitude": float,
     "reasoning": str,
}
```

Field semantics:

- `embedding_similarity`: Stage 1 topical similarity score
- `direction`: `-1.0` means evidence toward NO, `+1.0` means evidence toward YES
- `magnitude`: strength of evidence from `0.0` to `1.0`
- `reasoning`: LLM explanation for downstream display, ranking, or auditing

### Recommended Integration Pattern

If the next stage wants progressive results, use the streaming interface directly.

```python
from pipeline.affinity_pipeline import AffinityPipeline
from pipeline.config import PipelineConfig

config = PipelineConfig(
     affinity_embedding_threshold=0.50,
     llm_provider="anthropic",
     llm_model="claude-sonnet-4-20250514",
)

pipe = AffinityPipeline(config)
stage1_candidates = pipe.stage1(events, predictions)

for result_dict in pipe.stream(stage1_candidates):
     handle_downstream(result_dict)
```

If the next stage wants a full in-memory list instead:

```python
candidates, results = pipe.run(events, predictions)
```

`results` is a `list[dict]`, not a list of Pydantic objects.

### CLI Usage

Show help:

```powershell
sentimentree --help
```

Run the original enrichment pipeline:

```powershell
sentimentree run
```

Search ChromaDB:

```powershell
sentimentree search "Iran war" -n 5
sentimentree search "regulation" --source news_rss
```

Run affinity scoring without LLM calls:

```powershell
sentimentree affinity events_example.json polymarket_preds.json --skip-llm
```

Run full affinity scoring:

```powershell
sentimentree affinity events_example.json polymarket_preds.json
```

Write JSON results to disk:

```powershell
sentimentree affinity events_example.json polymarket_preds.json -o affinity_results.json
```

## Current Defaults

The central defaults live in `pipeline/config.py`.

Important current values:

- `embedding_model = "BAAI/bge-small-en-v1.5"`
- `relevance_threshold = 0.55`
- `affinity_embedding_threshold = 0.50`
- `llm_provider = "anthropic"`
- `llm_model = "claude-sonnet-4-20250514"`
- `llm_temperature = 0.1`

If another stage depends on score calibration, do not silently change these defaults. In particular, threshold tuning is model-dependent.

## Integration Notes By Neighbor Stage

### Upstream Ingestion / Event Generation

Provide clean, normalized event text. The affinity pipeline performs better when:

- `Title` is short and factual
- `Description` captures the event summary without duplication
- `Sources[].Summary` contains concise evidence, not raw HTML or noise

Low-quality summaries will directly degrade both embedding similarity and LLM reasoning quality.

### Downstream Ranking / Clustering / UI

Recommended usage:

- Use `embedding_similarity` as a cheap first-pass relevance signal
- Use `direction * magnitude` as a rough signed impact score
- Preserve `reasoning` for user-visible explanations or review tooling
- Keep `event_id` and `prediction_id` unchanged for joins with upstream records

One practical signed score is:

```python
impact_score = result["direction"] * result["magnitude"]
```

This is not built into the pipeline, but it is a reasonable downstream feature.

## Known Operational Constraints

- The first model load can be slow because transformer weights download on demand.
- Hugging Face warnings about unauthenticated requests are expected unless `HF_TOKEN` is configured.
- The LLM scorer expects valid JSON back from the model and strips code fences defensively.
- The current affinity tests are lighter than the original pipeline tests. Treat the affinity path as functional but still worth expanding.
- `.env` must contain a valid provider key for full Stage 2 execution.

## Fast Sanity Checks

Verify the CLI is installed:

```powershell
sentimentree --help
```

Verify Stage 1 only:

```powershell
sentimentree affinity events_example.json polymarket_preds.json --skip-llm
```

Verify original pipeline tests:

```powershell
pytest tests/test_pipeline_stages.py -q
```

## What Another Agent Should Not Assume

- Do not assume the original text enrichment pipeline and the event to prediction pipeline share the same output schema.
- Do not assume the CLI name is `sentimenttree`; the registered command is `sentimentree`.
- Do not assume Stage 2 returns Pydantic models; the streaming interface yields plain dictionaries.
- Do not assume Python 3.13 compatibility.

## Suggested Next Integration Points

If you are extending this stage into the rest of the app, the cleanest seams are:

1. Upstream adapter that normalizes Role 1 event payloads into `Event`.
2. Prediction market adapter that normalizes Polymarket and Kalshi data into `Prediction`.
3. Downstream scorer or brancher that consumes the dicts from `AffinityPipeline.stream(...)`.
4. A persistence layer for storing affinity results keyed by `event_id` and `prediction_id`.
