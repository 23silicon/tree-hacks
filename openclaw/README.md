# OpenClaw Compatibility Layer

This folder defines the OpenClaw compatibility contract that powers the local orchestration flow in this repository.

Status: active and used by the local API orchestration loop.

## What is here
- `openclaw.manifest.json`: task and capability manifest
- `contracts/pipeline-input.schema.json`: expected ingestion payload
- `contracts/pipeline-output.schema.json`: expected enrichment payload

## How this is used in the running system
- The frontend sends workflow requests to local `/api` routes.
- Vite proxies `/api` requests to the local FastAPI service.
- FastAPI executes scraping, prediction retrieval, enrichment, and graph assembly.
- OpenClaw contracts define the canonical input/output shape that this runtime path follows.

In short: OpenClaw is the contract and orchestration surface, and the local server is the execution engine.

## Runtime mapping
- Ingest contract: `openclaw/contracts/pipeline-input.schema.json`
- Emit contract: `openclaw/contracts/pipeline-output.schema.json`
- API execution routes: `/workflow/run`, `/workflow/run/stream`, `/workflow/live/stream`
- Prediction routes: `/predictions/search`, `/predictions/search/stream`

## Evidence of Runtime Use

Local execution can be verified with a direct call into the workflow route:

```bash
curl -X POST "http://127.0.0.1:8000/workflow/run" \
	-H "Content-Type: application/json" \
	-d '{"query":"iran war","prediction_limit":8,"include_social":true,"bluesky_seconds":3}'
```

The API response includes OpenClaw-aligned outputs:

- `sources.posts`
- `sources.predictions`
- `sources.events`
- `sources.enriched_items`
- `sources.affinity_results`
- `graph.nodes`
- `graph.edges`

This is the concrete runtime realization of OpenClaw in this repository: contract-driven orchestration through a local API execution path.

## Contract-Aligned Payload Examples

Ingest payload:

```json
{
	"contract_id": "demo-iran-war",
	"query": "iran war",
	"sources": ["news", "social", "markets"],
	"time_window": {
		"start": "2026-03-20T00:00:00Z",
		"end": "2026-03-29T00:00:00Z"
	}
}
```

Emit payload:

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

## Execution policy
- Planning and analysis against this folder is allowed and encouraged.
- Mutation of core application folders is blocked unless a human reviewer explicitly approves.
