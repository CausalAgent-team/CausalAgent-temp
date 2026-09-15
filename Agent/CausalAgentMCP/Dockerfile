FROM python:3.11-slim

WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=5 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       g++ \
       git \
       default-libmysqlclient-dev \
       pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-base.txt /tmp/requirements-base.txt
COPY Agent/CausalAgentMCP/requirements.txt /tmp/causal-mcp-requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements-base.txt \
    && pip install --no-cache-dir -r /tmp/causal-mcp-requirements.txt \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
       torch==2.7.1+cpu \
    && pip install --no-cache-dir --no-deps \
       git+https://github.com/DMIRLAB-Group/CDMIR.git@7caa64a819e8699243bbe4a54e623626f7801a40

COPY Agent ./Agent
COPY app ./app
COPY config ./config
COPY Database ./Database
COPY observability ./observability

EXPOSE 8080

CMD ["python", "-m", "Agent.CausalAgentMCP.app"]
