# Spatial Accessibility Pipeline
# ================================
# To run a different city/facility: make run CONFIG=configs/nyc_rhc.yaml

.PHONY: help install setup clean test pytest run visualize docker-build docker-run

CONFIG ?= config.yaml

help:
	@echo "Spatial Accessibility Pipeline"
	@echo "==============================="
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install Python dependencies"
	@echo "  make setup            Create required directories"
	@echo ""
	@echo "Pipeline:"
	@echo "  make run              Run full pipeline (uses CONFIG=config.yaml)"
	@echo "  make run CONFIG=configs/nyc_rhc.yaml  Run with alternate config"
	@echo "  make visualize        Regenerate map from existing Gold layer"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Validate environment (imports + data)"
	@echo "  make pytest           Run full test suite with coverage"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     Build Docker image"
	@echo "  make docker-run       Run pipeline in Docker"
	@echo ""

install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt
	@echo "Done"

setup:
	@echo "Creating project directories..."
	mkdir -p data/intermediate_files data/reference
	mkdir -p outputs/results outputs/figures
	mkdir -p logs
	@echo "Done"

clean:
	@echo "Cleaning outputs..."
	rm -rf outputs/results/bronze outputs/results/silver outputs/results/gold
	rm -f outputs/results/*.csv outputs/results/*.parquet outputs/results/*.duckdb
	rm -f outputs/figures/*.png
	rm -f logs/*.log
	@echo "Done"

# Run the full pipeline
run:
	@echo "Running pipeline with config: $(CONFIG)"
	python run_pipeline.py --config $(CONFIG)

# Regenerate visualisation only (requires existing Gold layer)
visualize:
	@python -c "\
from pipeline.config import load_config; \
from pipeline.store.s3_store import read_layer; \
from pipeline.visualize import plot_accessibility_map; \
cfg = load_config(); \
result = read_layer('gold', 'scores', config=cfg); \
fac = read_layer('silver', 'facilities', config=cfg); \
p = plot_accessibility_map(result, fac, config=cfg); \
print('Map saved:', p)"

# Environment validation (does not require data)
test:
	@echo "Validating environment..."
	@python -c "import geopandas, pandas, numpy, scipy, duckdb; print('Core imports OK')" \
		|| (echo "Missing core dependencies — run: make install" && exit 1)
	@python -c "import boto3; print('boto3 OK')" \
		|| echo "boto3 not installed (optional — only needed for S3)"
	@python -c "import airflow; print('Airflow OK')" \
		|| echo "Airflow not installed (optional — only needed for DAG)"
	@python -c "from pipeline.config import load_config; cfg = load_config(); area = cfg.get('study_area', {}).get('name', 'unknown-area'); facility = cfg.get('facility', {}).get('label') or cfg.get('cms', {}).get('facility_type', 'unknown-facility'); print('Config OK:', area, '|', facility)"
	@echo "Environment OK"

# Full test suite
pytest:
	@echo "Running test suite..."
	python -m pytest tests/ -v --tb=short --cov=pipeline --cov-report=term-missing

# Docker
docker-build:
	docker build -t spatial-accessibility:latest .
	@echo "Docker image built"

docker-run:
	docker run --rm \
		-v $$(pwd)/outputs:/app/outputs \
		-v $$(pwd)/config.yaml:/app/config.yaml \
		--env-file .env \
		spatial-accessibility:latest \
		python run_pipeline.py
