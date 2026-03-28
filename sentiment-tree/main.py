"""CLI entry point for the SentimentTree embedding pipeline."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import click

from pipeline.config import PipelineConfig
from pipeline.embedder import Embedder
from pipeline.models import RawItem
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
@click.option("--threshold", default=0.25, help="Relevance threshold (0-1).")
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


if __name__ == "__main__":
    cli()
