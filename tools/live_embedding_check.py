#!/usr/bin/env python3
"""One approved Vertex embedding smoke check; never runs during offline tests."""
from __future__ import annotations

import argparse
import json
import os

from google import genai
from google.genai.types import EmbedContentConfig


MODEL = "gemini-embedding-001"
LOCATION = "global"


def embedding(client, text: str, task_type: str) -> list[float]:
    response = client.models.embed_content(
        model=MODEL,
        contents=text,
        config=EmbedContentConfig(task_type=task_type),
    )
    if not response.embeddings or not response.embeddings[0].values:
        raise RuntimeError("Vertex returned an empty embedding")
    return [float(value) for value in response.embeddings[0].values]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed one skill and one query with Vertex gemini-embedding-001."
    )
    parser.add_argument(
        "--approved",
        action="store_true",
        help="Confirm the account holder approved these two live Vertex requests.",
    )
    args = parser.parse_args()
    if not args.approved:
        raise SystemExit("Live provider call not made: rerun with --approved after approval.")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit("GOOGLE_CLOUD_PROJECT is required")
    client = genai.Client(vertexai=True, project=project, location=LOCATION)
    skill_vector = embedding(
        client,
        "Break a large task into the smallest concrete next action.",
        "RETRIEVAL_DOCUMENT",
    )
    query_vector = embedding(client, "How should I start this task?", "RETRIEVAL_QUERY")
    print(
        json.dumps(
            {
                "model": MODEL,
                "location": LOCATION,
                "skill_dimensions": len(skill_vector),
                "query_dimensions": len(query_vector),
                "non_empty": bool(skill_vector and query_vector),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
