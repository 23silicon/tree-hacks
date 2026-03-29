# Sentimentree

Public sentiment graph explorer with a Vite frontend and a FastAPI orchestration backend.

## OpenClaw Implementation in This Repo

Sentimentree uses an OpenClaw-aligned orchestration model in production development flow:

- OpenClaw contracts define the canonical ingest/emit payloads.
- The local FastAPI server is the runtime conductor for scraping and analysis.
- The frontend triggers workflows through local `/api` calls.
- The resulting payload is returned as graph-ready data for the timeline UI.

This means OpenClaw is not just documented here. It is formalized as the interface contract that governs how local data collection and enrichment workflows are executed.

### Runtime path

1. Frontend calls `/api/workflow/run` or streaming workflow endpoints.
2. Vite proxy forwards requests to local FastAPI.
3. FastAPI coordinates sourcing, prediction lookup, relevance and sentiment analysis, and graph construction.
4. Responses are aligned with the OpenClaw compatibility contracts under `openclaw/contracts/`.

## Two-Minute Demo Flow

Run both services from the repo root:

```bash
./run-all.sh
```

Then run a workflow request against the local API:

```bash
curl -X POST "http://127.0.0.1:8000/workflow/run" \
	-H "Content-Type: application/json" \
	-d '{
		"query": "iran war",
		"prediction_limit": 8,
		"include_social": true,
		"bluesky_seconds": 3
	}'
```

Expected response shape:

```json
{
	"query": "iran war",
	"sources": {
		"posts": [],
		"predictions": [],
		"events": [],
		"enriched_items": [],
		"affinity_results": []
	},
	"graph": {
		"nodes": [],
		"edges": []
	}
}
```

This demonstrates the full OpenClaw-aligned local loop: request ingestion, multi-source scraping, enrichment, and graph payload emission.

## OpenClaw Contract Conformance

The runtime is implemented to follow the OpenClaw compatibility contracts in `openclaw/contracts/`.

Input contract example (`pipeline-input.schema.json`):

```json
{
	"contract_id": "demo-iran-war",
	"query": "iran war",
	"sources": ["news", "social", "markets"],
	"time_window": {
		"start": "2026-03-20T00:00:00Z",
		"end": "2026-03-29T00:00:00Z"
	},
	"sampling": {
		"max_items": 500,
		"priority": "high"
	}
}
```

Output contract example (`pipeline-output.schema.json`):

```json
{
	"contract_id": "demo-iran-war",
	"generated_at": "2026-03-29T12:00:00Z",
	"nodes": [
		{
			"id": "evt_001",
			"timestamp": "2026-03-28T19:00:00Z",
			"source": "google_news",
			"sentiment": -0.41,
			"summary": "Military escalation reports increased market uncertainty.",
			"tags": ["military", "markets", "escalation"]
		}
	],
	"edges": [
		{
			"source": "evt_001",
			"target": "evt_002",
			"kind": "causal"
		}
	]
}
```

## Shared Backend Runtime

The Python components are meant to share one repo-level virtual environment:

```bash
make python-setup
source .venv/bin/activate
```

Then run the API from the repo root:

```bash
make api-dev
```

The frontend talks to that API through the Vite proxy at `/api`.
