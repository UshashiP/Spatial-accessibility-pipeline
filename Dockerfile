# Multi-stage Dockerfile for Healthcare Accessibility Analysis Pipeline
# Python 3.12 + GeoPandas + PostGIS connectivity

# ============================================================================
# Stage 1: Base Image with System Dependencies
# ============================================================================
FROM python:3.12-slim-bookworm AS base

LABEL maintainer="Healthcare Accessibility Research"
LABEL description="Geospatial accessibility analysis with PostGIS integration"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies for geospatial libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    # GDAL/OGR for geospatial data
    gdal-bin \
    libgdal-dev \
    # GEOS for geometry operations
    libgeos-dev \
    libgeos++-dev \
    # PROJ for coordinate transformations
    proj-bin \
    libproj-dev \
    # Spatial indexing
    libspatialindex-dev \
    # PostgreSQL client
    postgresql-client \
    libpq-dev \
    # Build essentials
    gcc \
    g++ \
    make \
    # Utilities
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL library path
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash researcher && \
    mkdir -p /app /data /outputs && \
    chown -R researcher:researcher /app /data /outputs

WORKDIR /app

# ============================================================================
# Stage 2: Python Dependencies
# ============================================================================
FROM base AS dependencies

USER researcher

# Copy only requirements first (layer caching optimization)
COPY --chown=researcher:researcher requirements.txt .

# Install Python dependencies
RUN pip install --user --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 3: Application Code
# ============================================================================
FROM dependencies AS application

USER researcher

# Copy application code
COPY --chown=researcher:researcher scripts/ ./scripts/
COPY --chown=researcher:researcher config.yaml .
COPY --chown=researcher:researcher Makefile .

# Copy data (or mount as volume in production)
COPY --chown=researcher:researcher data/ ./data/

# Create output directories
RUN mkdir -p outputs/results outputs/figures

# ============================================================================
# Stage 4: Test Runner
# ============================================================================
FROM dependencies AS test

USER researcher

# Copy pipeline package + tests
COPY --chown=researcher:researcher pipeline/ ./pipeline/
COPY --chown=researcher:researcher tests/ ./tests/
COPY --chown=researcher:researcher config.yaml .
COPY --chown=researcher:researcher dags/ ./dags/

# Add Python packages to PATH
ENV PATH=/home/researcher/.local/bin:$PATH

# Run pytest by default; CI overrides CMD with coverage flags
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]

# ============================================================================
# Stage 5: Production Image (Minimal)
# ============================================================================
FROM base AS production

USER researcher

# Copy Python dependencies from dependencies stage
COPY --from=dependencies /home/researcher/.local /home/researcher/.local

# Copy pipeline package + supporting assets
COPY --chown=researcher:researcher pipeline/ ./pipeline/
COPY --chown=researcher:researcher dags/ ./dags/
COPY --chown=researcher:researcher scripts/ ./scripts/
COPY --chown=researcher:researcher config.yaml .
COPY --chown=researcher:researcher Makefile .

# Create necessary directories
RUN mkdir -p data/shapefiles outputs/results outputs/figures logs

# Add Python packages to PATH
ENV PATH=/home/researcher/.local/bin:$PATH

# Health check: verify the pipeline package is importable
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import pipeline; import pipeline.config" || exit 1

# Expose port for FastAPI (when implemented)
EXPOSE 8000

# Default command: run all accessibility methods
CMD ["make", "run-all"]

# ============================================================================
# Alternative Entrypoints (override with docker run --entrypoint)
# ============================================================================

# Run specific methods:
# docker run --entrypoint make accessibility:latest run-enhanced
# docker run --entrypoint make accessibility:latest run-gravity

# Interactive mode:
# docker run -it --entrypoint /bin/bash accessibility:latest

# API mode (future):
# docker run -p 8000:8000 --entrypoint uvicorn accessibility:latest app.main:app --host 0.0.0.0
