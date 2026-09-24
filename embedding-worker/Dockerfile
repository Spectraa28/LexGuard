FROM python:3.12-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PIP_RETRIES=10 \
    HF_HOME=/models/huggingface

WORKDIR /app

# Shared by the API and worker. The +cpu wheel avoids multi-gigabyte CUDA layers.
FROM runtime-base AS embedding-base
COPY requirements-torch.txt requirements-embedding.txt ./
RUN pip install --no-cache-dir -r requirements-torch.txt
RUN pip install --no-cache-dir -r requirements-embedding.txt

FROM embedding-base AS worker
COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY . .
CMD ["python", "worker.py"]

FROM embedding-base AS api
COPY requirements-api-framework.txt requirements-api.txt ./
RUN pip install --no-cache-dir --no-deps -r requirements-api-framework.txt
RUN pip install --no-cache-dir -r requirements-api.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
