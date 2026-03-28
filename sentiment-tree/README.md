# SentimentTree — Embedding Pipeline (Role 2)

Embedding, tagging, relevance filtering, directional sentiment analysis, and semantic search pipeline for the SentimentTree project.

## Architecture

```
Raw Items (Role 1)
       │
       ▼
  ┌──────────┐
  │ Embedder │  sentence-transformers (all-MiniLM-L6-v2)
  └────┬─────┘
       │ vectors
       ▼
  ┌──────────────────┐
  │ Relevance Filter │  cosine similarity vs. contract question
  └────┬─────────────┘
       │ relevant items only
       ▼
  ┌───────────────────┐
  │ Sentiment Scorer  │  zero-shot classification (BART-MNLI)
  └────┬──────────────┘   directional: yes/no relative to contract
       │
       ▼
  ┌────────┐
  │ Tagger │  spaCy NER + keyword topic tagging
  └────┬───┘
       │
       ▼
  ┌──────────────┐
  │ Vector Store │  ChromaDB (persistent, cosine distance)
  └────┬─────────┘
       │
       ▼
  Enriched Items (Role 3)  +  Semantic Search API
```

## Setup

```bash
cd sentiment-tree

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm
```

## Usage

### Run pipeline on sample data

```bash
python main.py run
```

This processes 5 sample items against the contract question "Will Bitcoin reach $100k by end of 2026?", filters for relevance, scores directional sentiment, extracts entities/tags, and stores to ChromaDB.

### Search stored items

```bash
python main.py search "institutional buying"
python main.py search "regulation" --source news_rss
```

### Show pipeline info

```bash
python main.py info
```

### Adjust relevance threshold

```bash
python main.py run --threshold 0.3
```

## Data Models

### Input: `RawItem` (from Role 1)

| Field       | Type     | Description                   |
|-------------|----------|-------------------------------|
| `text`      | str      | Scraped content               |
| `source`    | str      | Platform (reddit, x, etc.)    |
| `timestamp` | datetime | ISO 8601                      |
| `url`       | str      | Source URL                     |

### Output: `EnrichedItem` (to Role 3)

| Field                  | Type        | Description                                    |
|------------------------|-------------|------------------------------------------------|
| `text`                 | str         | Original text                                  |
| `source`               | str         | Platform                                       |
| `timestamp`            | datetime    | Original timestamp                             |
| `url`                  | str         | Source URL                                      |
| `embedding`            | list[float] | Semantic embedding vector                      |
| `sentiment_score`      | float       | Directional sentiment, -1 (no) to 1 (yes)     |
| `sentiment_confidence` | float       | Confidence 0-1                                 |
| `topic_tags`           | list[str]   | Topic labels                                   |
| `entities`             | list[str]   | Named entities                                 |
| `relevance_score`      | float       | Cosine similarity to contract question (0-1)   |

## Pipeline Components

| Module               | Class             | Purpose                                        |
|----------------------|-------------------|------------------------------------------------|
| `pipeline/embedder.py`          | `Embedder`          | Sentence-transformer embeddings       |
| `pipeline/relevance_filter.py`  | `RelevanceFilter`   | Cosine similarity filtering           |
| `pipeline/sentiment_scorer.py`  | `SentimentScorer`   | Zero-shot directional sentiment       |
| `pipeline/tagger.py`            | `Tagger`            | spaCy NER + topic tagging             |
| `pipeline/vector_store.py`      | `VectorStore`       | ChromaDB storage and retrieval        |
| `pipeline/semantic_search.py`   | `SemanticSearch`    | Natural language search interface     |
| `pipeline/pipeline.py`          | `Pipeline`          | Full pipeline orchestrator            |

## Configuration

All defaults in `pipeline/config.py`. Override by passing a `PipelineConfig` instance:

```python
from pipeline.config import PipelineConfig
from pipeline.pipeline import Pipeline

config = PipelineConfig(
    relevance_threshold=0.3,
    embedding_model="all-MiniLM-L6-v2",
    sentiment_model="facebook/bart-large-mnli",
)
pipe = Pipeline("Will X happen?", config=config)
```

## Programmatic Usage

```python
from datetime import datetime, timezone
from pipeline.models import RawItem
from pipeline.pipeline import Pipeline

pipe = Pipeline("Will Bitcoin reach $100k by end of 2026?")

item = RawItem(
    text="Bitcoin ETF inflows hit $1B this week",
    source="news_rss",
    timestamp=datetime.now(timezone.utc),
    url="https://example.com/article",
)

enriched = pipe.process_single(item)
if enriched:
    print(f"Sentiment: {enriched.sentiment_score:+.4f}")
    print(f"Relevance: {enriched.relevance_score:.4f}")
    print(f"Entities:  {enriched.entities}")
```
