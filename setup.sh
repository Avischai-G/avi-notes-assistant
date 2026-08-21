#!/usr/bin/env bash
# One-shot Vertex AI setup. Run AFTER `gcloud auth login`.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-gen-lang-client-0256233370}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"

echo "==> project: $PROJECT   location: $LOCATION"

gcloud config set project "$PROJECT"
gcloud auth application-default login          # second, separate consent — the one people skip
gcloud auth application-default set-quota-project "$PROJECT"
gcloud services enable aiplatform.googleapis.com run.googleapis.com

cat > .env <<ENV
GOOGLE_CLOUD_PROJECT=$PROJECT
GOOGLE_CLOUD_LOCATION=$LOCATION
GOOGLE_GENAI_USE_VERTEXAI=true
ENV

echo "==> wrote .env"
echo "==> verifying Vertex reachability"
python3 - <<'PY'
import os
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT","gen-lang-client-0256233370"))
try:
    from google import genai
    c = genai.Client(vertexai=True,
                     project=os.environ["GOOGLE_CLOUD_PROJECT"],
                     location=os.environ.get("GOOGLE_CLOUD_LOCATION","us-central1"))
    r = c.models.generate_content(model="gemini-2.5-pro", contents="reply with exactly: VERTEX OK")
    print("   ", (r.text or "").strip())
except Exception as e:
    print("    NOT READY:", type(e).__name__, e)
PY
