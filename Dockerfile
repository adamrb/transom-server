FROM python:3.12-slim

WORKDIR /srv/plaud-bridge

COPY requirements.txt requirements-stt.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-stt.txt

COPY app ./app

RUN useradd -u 1000 -m appuser && mkdir -p /data && chown appuser /data
USER appuser

# Keep downloaded models inside the data volume so they survive rebuilds.
ENV PB_DATA_DIR=/data \
    HF_HOME=/data/models
VOLUME /data
EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
