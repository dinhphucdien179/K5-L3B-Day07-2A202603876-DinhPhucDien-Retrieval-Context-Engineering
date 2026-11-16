FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/workspace/.cache/huggingface

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt requirements-embedding.txt requirements-dev.txt /opt/requirements/
RUN python -m pip install --no-cache-dir 'torch==2.15.0+cpu' --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir \
        -r /opt/requirements/requirements.txt \
        -r /opt/requirements/requirements-embedding.txt \
        -r /opt/requirements/requirements-dev.txt \
    && python -m pip check

WORKDIR /workspace/starter
ENTRYPOINT ["python"]
CMD ["-m", "src.run", "preflight"]
