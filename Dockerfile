FROM python:3.12-slim AS runtime

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
RUN python -m pip install --no-cache-dir ".[detector]"

ENV YOLO_CONFIG_DIR=/tmp
ENV MPLCONFIGDIR=/tmp/matplotlib
ENV COURT4_DETECTOR_MODEL_SHA256=0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1

LABEL org.court4.detector-model.identifier="ultralytics-yolo11n-assets-v8.3.0" \
      org.court4.detector-model.sha256="0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1" \
      org.court4.detector-model.source="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"

COPY app ./app
COPY alembic.ini ./
COPY scripts ./scripts
COPY calibration ./calibration
COPY calibration-results.json CALIBRATION_REPORT.md CALIBRATION_DISAGREEMENTS.md ./
COPY calibration-readiness-integrity.json ./
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test

RUN python -m pip install --no-cache-dir ".[dev]"
COPY tests ./tests
COPY spike ./spike
COPY docker-compose.yml ./docker-compose.yml

FROM runtime AS final
