# API

FastAPI service that now acts as the main backend orchestration layer for the project.
It can:

- search Polymarket predictions
- source context from `data-sourcing/`
- call into `sentiment-tree/` when that stack is installed
- return graph-ready payloads for the frontend

## Shared Python Environment

Use one repo-level virtual environment for `api/`, `data-sourcing/`, and `sentiment-tree/`:

```bash
make python-setup
source .venv/bin/activate
```

That installs `../requirements.shared.txt`.

## Run The API

```bash
source .venv/bin/activate
uvicorn main:app --app-dir api --reload
```

## Endpoints

### Standard prediction search

```bash
curl "http://127.0.0.1:8000/predictions/search?query=iran&limit=5"
```

Or:

```bash
curl -X POST "http://127.0.0.1:8000/predictions/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"iran war","limit":5}'
```

### End-to-end workflow

This is the endpoint the frontend should call.

```bash
curl -X POST "http://127.0.0.1:8000/workflow/run" \
  -H "Content-Type: application/json" \
  -d '{"query":"iran war","prediction_limit":8,"bluesky_seconds":3}'
```

The response includes:

- `sources.posts`
- `sources.predictions`
- `sources.events`
- `sources.enriched_items`
- `sources.affinity_results`
- `graph.nodes`
- `graph.edges`

### Streaming NDJSON response

Prediction search streaming:

```bash
curl -N -X POST "http://127.0.0.1:8000/predictions/search/stream" \
  -H "Content-Type: application/json" \
  -d '{"query":"iran war","limit":5}'
```

Workflow streaming:

```bash
curl -N -X POST "http://127.0.0.1:8000/workflow/run/stream" \
  -H "Content-Type: application/json" \
  -d '{"query":"iran war","prediction_limit":8}'
```

## Notes

- The service tries to read live market data from Polymarket's Gamma API.
- If the upstream request fails or returns no relevant matches, it falls back to `../sentiment-tree/polymarket_preds.json`.
- If the full `sentiment-tree` model stack is not installed, the workflow still returns posts, predictions, and a graph using fallback event synthesis.
