# API

Minimal FastAPI service for searching Polymarket predictions by a free-text query.

## Run

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Endpoints

### Standard JSON response

```bash
curl "http://127.0.0.1:8000/predictions/search?query=iran&limit=5"
```

Or:

```bash
curl -X POST "http://127.0.0.1:8000/predictions/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"iran war","limit":5}'
```

### Streaming NDJSON response

This streams newline-delimited JSON objects. Each line has a `type` field:
`status`, `prediction`, `complete`, or `error`.

```bash
curl -N -X POST "http://127.0.0.1:8000/predictions/search/stream" \
  -H "Content-Type: application/json" \
  -d '{"query":"iran war","limit":5}'
```

## Notes

- The service tries to read live market data from Polymarket's Gamma API.
- If the upstream request fails or returns no relevant matches, it falls back to `../sentiment-tree/polymarket_preds.json`.
- The fallback loader tolerates the extra leading characters currently present in that JSON file.
