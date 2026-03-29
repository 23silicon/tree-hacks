# Sentimentree

Public sentiment graph explorer with a Vite frontend and a FastAPI orchestration backend.

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
