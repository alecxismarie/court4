PYTHON ?= python

.PHONY: install test lint format format-check typecheck run inspect calibrate track select-player analyze docker-build

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

format-check:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy app scripts tests

run:
	$(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

inspect:
	$(PYTHON) -m scripts.inspect_video --input data/input/match.mp4

calibrate:
	$(PYTHON) -m scripts.calibrate_court \
		--input $(INPUT) \
		--near-left $(NEAR_LEFT) \
		--near-right $(NEAR_RIGHT) \
		--far-right $(FAR_RIGHT) \
		--far-left $(FAR_LEFT)

track:
	$(PYTHON) -m scripts.track_players \
		--input $(INPUT) \
		--calibration $(CALIBRATION) \
		--analysis-id $(ANALYSIS_ID)

select-player:
	$(PYTHON) -m scripts.select_player \
		--tracking-report $(TRACKING_REPORT) \
		--track-id $(TRACK_ID)

analyze:
	$(PYTHON) -m scripts.analyze_match \
		--analysis-id $(ANALYSIS_ID)

docker-build:
	docker build -t court4:local .
