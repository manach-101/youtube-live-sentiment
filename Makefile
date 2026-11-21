PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin

.PHONY: setup test demo pipeline ingest clean-demo

setup:            ## Create virtualenv and install pinned dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

test:             ## Run the test suite (offline)
	$(BIN)/python -m pytest -q

demo:             ## Run Silver + Gold on the synthetic fixtures into data/demo/
	$(BIN)/python -m src.pipeline --raw-dir tests/fixtures/raw --data-dir data/demo

pipeline:         ## Run Silver + Gold on raw/ into data/
	$(BIN)/python -m src.pipeline

ingest:           ## Live ingestion (needs YOUTUBE_API_KEY). Usage: make ingest VIDEO_ID=xxxx ARGS="--duration 300"
	$(BIN)/python -m src.youtube_ingest --video-id $(VIDEO_ID) $(ARGS)

clean-demo:
	rm -rf data/demo
