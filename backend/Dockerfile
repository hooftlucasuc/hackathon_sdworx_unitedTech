# CallSight backend for Cloud Run. Build context: backend/
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# vertex (default, lean image) or local (bundles sentence-transformers + the model, larger image).
ARG EMBEDDING_PROVIDER=vertex
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
# where sentence-transformers caches the model; baked into the image so Cloud Run has no cold download
ENV HF_HOME=/srv/models SENTENCE_TRANSFORMERS_HOME=/srv/models

WORKDIR /srv
RUN useradd --uid 10001 --no-create-home appuser

# Order matters for the build cache (infra/cloudbuild.backend.yaml builds with --cache-from :latest):
# dependencies and the model only rebuild when pyproject.toml or EMBEDDING_MODEL change, a code
# change only reruns the last two layers.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && if [ "$EMBEDDING_PROVIDER" = "local" ]; then \
         pip install --index-url https://download.pytorch.org/whl/cpu torch \
         && pip install ".[local]"; \
       else pip install .; fi \
    && rm -rf app build *.egg-info

# pre-download the embedding model at build time (only for the local provider); chown in the same
# layer, a separate `chown -R` would copy the whole model into a new layer on every build
RUN mkdir -p /srv/models \
    && if [ "$EMBEDDING_PROVIDER" = "local" ]; then \
         python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('$EMBEDDING_MODEL')"; \
       fi \
    && chown -R appuser /srv/models
# the model is baked in: no Hugging Face lookups on a cold start
ENV HF_HUB_OFFLINE=1

COPY app ./app
COPY samples ./samples
RUN pip install --no-deps .

USER appuser

# Cloud Run injects PORT (8080 by default)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
