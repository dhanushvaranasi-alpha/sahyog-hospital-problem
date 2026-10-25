# One image for the API and the ingest worker (infra/docker-compose.yml runs both).
# python:3.12 matches requires-python; the slim-trixie tag takes 3.12 security patches.
FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/models
WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir . \
 && pip install --no-cache-dir https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl

COPY services ./services
COPY evals ./evals
COPY data/__init__.py data/load.py ./data/
COPY data/transforms ./data/transforms
COPY data/synthetic ./data/synthetic
COPY data/reference ./data/reference
COPY infra/db/init ./infra/db/init

EXPOSE 8000
CMD ["uvicorn", "--factory", "services.api.app:create_production_app", "--host", "0.0.0.0", "--port", "8000"]
