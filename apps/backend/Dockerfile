FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=staging \
    EMBEDDING_ENABLED=true \
    EMBEDDING_PROVIDER=local_e5 \
    EMBEDDING_DIMENSIONS=768 \
    LOCAL_SEMANTIC_SEARCH_ENABLED=true \
    LOCAL_E5_MODEL_PATH=/opt/e5-model \
    LOCAL_E5_MODEL_REVISION=61ed0e3e5b5906e6bd8196f55df9293e4ca28eeaa270c1bcdb43ef610b976870 \
    RUN_E5_BACKFILL_ON_STARTUP=true \
    RUN_STAGING_SEED=true

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements-local-e5.txt requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements-local-e5.txt

# Public, immutable Hugging Face source revision. Only runtime files are retained;
# no model cache or credentials are copied into the image.
RUN python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="intfloat/multilingual-e5-base",
    revision="d128750597153bb5987e10b1c3493a34e5a4502a",
    local_dir="/opt/e5-model",
    allow_patterns=[
        ".gitattributes", "1_Pooling/config.json", "README.md", "config.json",
        "model.safetensors", "modules.json", "sentence_bert_config.json",
        "sentencepiece.bpe.model", "special_tokens_map.json", "tokenizer.json",
        "tokenizer_config.json",
    ],
)
PY
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
COPY . .
RUN rm -rf /opt/e5-model/.cache \
    && test "$(PYTHONPATH=/app python -m embeddings.providers.local_e5 /opt/e5-model 2>/dev/null | tail -n 1)" = "61ed0e3e5b5906e6bd8196f55df9293e4ca28eeaa270c1bcdb43ef610b976870" \
    && chown -R app:app /app /opt/e5-model
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready/', timeout=4)"]

CMD ["sh", "-c", "if [ \"$RUN_MIGRATIONS_ON_STARTUP\" = \"true\" ]; then alembic upgrade head; fi; if [ \"$RUN_STAGING_SEED\" = \"true\" ]; then python scripts/seed_staging_catalogue.py; fi; if [ \"$RUN_E5_BACKFILL_ON_STARTUP\" = \"true\" ]; then python scripts/embedding_backfill.py --kind product --limit 500; fi; exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
