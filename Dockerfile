FROM node:22-bookworm-slim AS node-runtime

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# notion-mcp-server requires Node >=20 and runs as a local stdio child.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libatomic1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version \
    && npm --version

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts \
    && npm cache clean --force

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY web ./web
COPY server.py ./

# Cloud Run provides the project and mounts the dedicated knowledge bucket at
# /knowledge. These eligibility-critical values are intentionally fixed.
ENV PORT=8080 \
    CORONER_MODEL=gemini-3.7-flash \
    GOOGLE_CLOUD_LOCATION=global \
    GOOGLE_GENAI_USE_VERTEXAI=true \
    TASK_STORE_MODE=notion
CMD exec uvicorn server:api --host 0.0.0.0 --port $PORT --workers 1
