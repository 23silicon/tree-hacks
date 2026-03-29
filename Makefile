PYTHON_VENV=.venv
PYTHON_BIN=$(PYTHON_VENV)/bin/python
PIP_BIN=$(PYTHON_VENV)/bin/pip

.PHONY: python-setup api-dev frontend-dev

python-setup:
	python3 -m venv $(PYTHON_VENV)
	$(PIP_BIN) install -r requirements.shared.txt

api-dev:
	$(PYTHON_VENV)/bin/uvicorn main:app --app-dir api --reload

frontend-dev:
	cd frontend && npm run dev
