# CallSight luisteraar voor Cloud Run: segment_collector.py + listen.html. Build context: scripts/
# Alleen stdlib (extractor rules), dus geen pip install: de build duurt seconden.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    EXTRACTOR=rules

WORKDIR /srv/scripts
COPY segment_collector.py listen.html ./

RUN useradd --uid 10001 --no-create-home appuser
USER appuser

# Cloud Run geeft PORT mee; FORWARD_URL en ELEVENLABS_API_KEY komen uit de deploy (infra/cloudbuild.listener.yaml)
CMD ["python", "segment_collector.py"]
