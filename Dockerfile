FROM python:3.12-slim

WORKDIR /srv/plaud-bridge

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd -u 1000 -m appuser
USER appuser

ENV PB_DATA_DIR=/data
VOLUME /data
EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
