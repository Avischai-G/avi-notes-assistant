FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY web ./web
COPY data/fleet.json data/sample-trace.json ./data/
COPY server.py cli.py ./

# Cloud Run sets $PORT. One worker: the work is IO-bound on Vertex, and the
# autopsy streams, so concurrency inside the worker is what matters.
ENV PORT=8080
CMD exec uvicorn server:api --host 0.0.0.0 --port $PORT --workers 1
