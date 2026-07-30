FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir ".[dev,detector]"

ENV YOLO_CONFIG_DIR=/tmp
ENV MPLCONFIGDIR=/tmp/matplotlib

COPY app ./app
COPY alembic.ini ./
COPY scripts ./scripts
COPY tests ./tests
COPY calibration ./calibration
COPY calibration-results.json CALIBRATION_REPORT.md CALIBRATION_DISAGREEMENTS.md ./
COPY calibration-readiness-integrity.json ./
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
