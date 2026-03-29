#!/usr/bin/env python3

"""CLI entry point for the SentimentTree embedding pipeline."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()  # Load .env (CLAUDE_API_KEY, etc.)

from pipeline.config import PipelineConfig
from pipeline.embedder import Embedder
from pipeline.models import Event, Prediction, RawItem
from pipeline.pipeline import Pipeline
from pipeline.semantic_search import SemanticSearch
from pipeline.vector_store import VectorStore

SAMPLE_DATA: list[dict] = [
    {
        "text": "Bitcoin just broke through $95k resistance with massive volume. Institutional buying is accelerating and ETF inflows hit record highs this week.",
        "source": "reddit",
        "timestamp": "2026-03-20T14:30:00Z",
        "url": "https://reddit.com/r/bitcoin/example1",
    },
    {
        "text": "The Federal Reserve signaled potential rate cuts which historically correlates with crypto bull runs. BTC looking strong.",
        "source": "x",
        "timestamp": "2026-03-21T09:15:00Z",
        "url": "https://x.com/example/status/123",
    },
    {
        "text": "Major regulatory crackdown incoming — SEC is preparing new enforcement actions against crypto exchanges. This could tank the market.",
        "source": "news_rss",
        "timestamp": "2026-03-22T11:00:00Z",
        "url": "https://news.example.com/sec-crackdown",
    },
    {
        "text": "Bitcoin mining difficulty just hit an all-time high. Hash rate continues to climb, signaling miner confidence in future prices.",
        "source": "youtube",
        "timestamp": "2026-03-23T16:45:00Z",
        "url": "https://youtube.com/watch?v=example",
    },
    {
        "text": "New recipe for chocolate chip cookies — cream the butter and sugar first for best results.",
        "source": "reddit",
        "timestamp": "2026-03-24T08:00:00Z",
        "url": "https://reddit.com/r/baking/example",
    },
]

CONTRACT_QUESTION = "Will Bitcoin reach $100k by end of 2026?"


@click.group()
def cli() -> None:
    """SentimentTree Embedding Pipeline CLI."""


@cli.command()
@click.option("--threshold", default=0.55, help="Relevance threshold (0-1).")
def run(threshold: float) -> None:
    """Run the pipeline on sample data."""
    config = PipelineConfig(relevance_threshold=threshold)
    pipe = Pipeline(CONTRACT_QUESTION, config=config)

    raw_items = [RawItem(**d) for d in SAMPLE_DATA]

    click.echo(f"Processing {len(raw_items)} items...")
    click.echo(f"Contract: {CONTRACT_QUESTION}")
    click.echo(f"Relevance threshold: {config.relevance_threshold}")
    click.echo("-" * 60)

    enriched = pipe.process(raw_items, store=True)

    click.echo(f"\n{len(enriched)}/{len(raw_items)} items passed relevance filter.\n")

    for i, item in enumerate(enriched, 1):
        click.echo(f"--- Item {i} ---")
        click.echo(f"  Source:     {item.source}")
        click.echo(f"  Text:      {item.text[:80]}...")
        click.echo(f"  Relevance: {item.relevance_score:.4f}")
        click.echo(f"  Sentiment: {item.sentiment_score:+.4f} (conf: {item.sentiment_confidence:.4f})")
        click.echo(f"  Tags:      {item.topic_tags}")
        click.echo(f"  Entities:  {item.entities}")
        click.echo()

    click.echo(f"Stored {pipe.vector_store.count()} items in ChromaDB.")


@cli.command()
@click.argument("query")
@click.option("-n", "--num-results", default=5, help="Number of results.")
@click.option("--source", default=None, help="Filter by source platform.")
def search(query: str, num_results: int, source: str | None) -> None:
    """Search stored items by natural language query."""
    config = PipelineConfig()
    embedder = Embedder(config)
    store = VectorStore(config)
    searcher = SemanticSearch(embedder, store, config)

    click.echo(f"Searching for: {query!r}")
    if source:
        click.echo(f"Filtering by source: {source}")
    click.echo("-" * 60)

    results = searcher.search(query, n_results=num_results, source_filter=source)

    if not results:
        click.echo("No results found.")
        return

    for i, r in enumerate(results, 1):
        click.echo(f"\n--- Result {i} (similarity: {r.get('similarity', 'N/A'):.4f}) ---")
        click.echo(f"  Text:      {r['text'][:100]}...")
        click.echo(f"  Source:    {r.get('source', 'N/A')}")
        click.echo(f"  Sentiment: {r.get('sentiment_score', 'N/A')}")
        click.echo(f"  Tags:      {r.get('topic_tags', '')}")


@cli.command()
def info() -> None:
    """Show pipeline configuration and vector store stats."""
    config = PipelineConfig()
    store = VectorStore(config)

    click.echo("Pipeline Configuration:")
    click.echo(f"  Embedding model:   {config.embedding_model}")
    click.echo(f"  Sentiment model:   {config.sentiment_model}")
    click.echo(f"  spaCy model:       {config.spacy_model}")
    click.echo(f"  Relevance thresh:  {config.relevance_threshold}")
    click.echo(f"  ChromaDB path:     {config.chroma_persist_dir}")
    click.echo(f"  Collection:        {config.chroma_collection}")
    click.echo(f"  Items in store:    {store.count()}")


# ─── Affinity pipeline (event → prediction scoring) ─────────────────


@cli.command()
@click.argument("events_file", type=click.Path(exists=True))
@click.argument("predictions_file", type=click.Path(exists=True))
@click.option("--threshold", default=0.50, help="Stage 1 embedding similarity threshold.")
@click.option("--skip-llm", is_flag=True, help="Only run Stage 1 (embedding filter), skip LLM.")
@click.option("--output", "-o", default=None, help="Write results JSON to file.")
def affinity(
    events_file: str,
    predictions_file: str,
    threshold: float,
    skip_llm: bool,
    output: str | None,
) -> None:
    """Score how events relate to prediction market outcomes.

    Two-stage pipeline:
      Stage 1: Embedding cosine similarity (fast, filters ~80% of pairs)
      Stage 2: LLM reasoning (direction + magnitude + explanation)

    Example:
      python main.py affinity events_example.json polymarket_preds.json
      python main.py affinity events_example.json polymarket_preds.json --skip-llm
    """
    from pipeline.affinity_pipeline import AffinityPipeline

    # Load events
    with open(events_file, "r", encoding="utf-8") as f:
        events_raw = json.load(f)
    events = [Event(**e) for e in events_raw]

    # Load predictions (handle wrapper object with "predictions" key)
    with open(predictions_file, "r", encoding="utf-8") as f:
        preds_raw = json.load(f)
    if isinstance(preds_raw, dict) and "predictions" in preds_raw:
        preds_list = preds_raw["predictions"]
    elif isinstance(preds_raw, list):
        preds_list = preds_raw
    else:
        raise click.ClickException("Predictions file must be a list or {predictions: [...]}.")
    predictions = [Prediction(**p) for p in preds_list]

    config = PipelineConfig(affinity_embedding_threshold=threshold)
    pipe = AffinityPipeline(config)

    click.echo(f"Events:      {len(events)}")
    click.echo(f"Predictions: {len(predictions)}")
    click.echo(f"Total pairs: {len(events) * len(predictions)}")
    click.echo(f"Stage 1 threshold: {threshold}")
    click.echo("=" * 65)

    # Stage 1
    click.echo("\n── Stage 1: Embedding candidate filtering ──")
    candidates = pipe.stage1(events, predictions)

    click.echo(f"   {len(candidates)} / {len(events) * len(predictions)} pairs passed embedding filter\n")

    for event, pred, sim in candidates:
        click.echo(f"   {sim:.4f}  Event[{event.ID}] \"{event.Title[:40]}\"")
        click.echo(f"           ↔ \"{pred.question[:50]}\"")

    results: list[dict] = []

    if skip_llm:
        click.echo("\n   (--skip-llm flag set, skipping Stage 2)")
    elif candidates:
        click.echo("\n── Stage 2: LLM affinity scoring ──\n")
        for r in pipe.stream(candidates):
            results.append(r)
            arrow = "→ YES" if r["direction"] > 0 else "→ NO " if r["direction"] < 0 else "→ NEU"
            click.echo(f"   Event[{r['event_id']}] × Pred[{r['prediction_id']}]")
            click.echo(f"     Embedding sim: {r['embedding_similarity']:.4f}")
            click.echo(f"     Direction:     {r['direction']:+.2f} {arrow}")
            click.echo(f"     Magnitude:     {r['magnitude']:.2f}")
            click.echo(f"     Reasoning:     {r['reasoning'][:120]}...")
            click.echo()

    # Output JSON
    if output and results:
        Path(output).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        click.echo(f"\nResults written to {output}")
    elif output and not results:
        # Write stage 1 results if no LLM
        out_data = [
            {"event_id": e.ID, "prediction_id": p.id, "embedding_similarity": round(s, 4)}
            for e, p, s in candidates
        ]
        Path(output).write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        click.echo(f"\nStage 1 results written to {output}")


if __name__ == "__main__":
    cli()
