# Live Notion isolation decision record — 2026-08-24

**Status: superseded by Avi's explicit option 2 authorization.** The initial
failure below is retained as historical evidence. Avi authorized changing only
the isolation regression to accept exactly one configured data source and pages
parented to that same data source, while retaining the unfiltered search,
`has_more=false`, hard failures for everything else, and the exact five-operation
MCP allowlist.

## Boundary reached

Avi approved the exact one-time live acceptance trace. The first outward check
ran before any mutation or model call:

```sh
./.venv/bin/python scripts/notion_board_setup.py isolation
```

Observed result:

```text
ERROR: RuntimeError: Isolation regression: search must return exactly one object
```

The following discovery command still passed and exposed exactly the five pinned
operations:

```text
PASS: MCP tools and the five-operation allowlist are exact
```

## Redacted diagnostic

One further read-only call repeated the same `POST /v1/search` request and emitted
only safe structural metadata—never a title, object ID, token, or database ID:

```json
{
  "result_count": 2,
  "has_more": false,
  "has_next_cursor": false,
  "results": [
    {
      "object": "page",
      "parent_type": "data_source_id",
      "parent_matches_configured_database": true
    },
    {
      "object": "data_source",
      "parent_type": "database_id",
      "parent_matches_configured_database": true
    }
  ]
}
```

The page was not opened, titled, identified, or mutated. No board row was created,
changed, counted through the task adapter, or archived.

## Controlling contract

Current official Notion documentation states that unfiltered search without a
query returns all pages or data sources shared with the connection, and that an
object filter is required to limit results to data sources:

<https://developers.notion.com/reference/post-search>

Therefore the frozen assertion “unfiltered search returns exactly one object” is
incompatible with retaining any accessible row in the configured data source.

## Scope choices presented

1. Preserve the frozen Card 3 assertion and byte identity. Stop the live story;
   it cannot be green while the required pre-existing row remains accessible.
2. Obtain an explicit scope change allowing a row-aware isolation definition,
   such as exactly one configured data source plus only pages parented by that
   source, with `has_more=false`. This changes the frozen Card 3 boundary and its
   recorded hashes.

Recommendation: choose option 2 only through an explicit Avi scope decision. It
matches Notion's documented object model while still rejecting content outside
the configured data source. Do not silently substitute a filtered query or treat
the present failure as PASS.

## Decision and implementation

Avi explicitly authorized option 2 on 2026-08-24. Only
`scripts/notion_board_setup.py` changed. Its SHA-256 moved from
`aacfc5eee0cdf408f06cd07b62a79c2a1c8d4237f7e4e61d032af83e0be7ddbf`
to `f1f2d990fad25852f2ab30726fadd85daadf47b5c511e250ddef4ddc0dcfde3a`.
`tests/test_authorized_notion_isolation.py` adds integration-level coverage
without changing Card 3's preserved tests. Targeted verification observed
`27 passed`; see `card3-hashes.md` for the identity comparison.

## Mutation and billing state at this initial failed preflight

- Notion writes: **0**
- Vertex generation calls: **0**
- Vertex embedding calls: **0**
- Firestore writes: **0**
- Marker-owned rows created: **0**
- Cleanup required: **no**, because preparation never began

The later authorized rerun passed this boundary, prepared two marker rows, then
stopped at the separate Firestore startup failure. That run's mandatory cleanup
proved zero marker rows remained; see `live-acceptance-2026-08-24.md`.
