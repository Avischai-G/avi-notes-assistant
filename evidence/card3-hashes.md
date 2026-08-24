# Card 3 hash evidence

Source: Card `4b48fec2`, clone `coroner-card3`. The final comparison used both
`cmp -s` and SHA-256 on 2026-08-24.

## Authorized isolation-regression change

On 2026-08-24 Avi explicitly authorized option 2: retain unfiltered
`POST /v1/search`, but accept the one configured data source plus only pages
whose `data_source_id` parent matches it, still requiring `has_more=false`.
This superseded byte identity for the isolation-regression file only.

| File | Card 3 SHA-256 (old) | Release SHA-256 (new) | Result |
|---|---|---|---|
| `scripts/notion_board_setup.py` | `aacfc5eee0cdf408f06cd07b62a79c2a1c8d4237f7e4e61d032af83e0be7ddbf` | `f1f2d990fad25852f2ab30726fadd85daadf47b5c511e250ddef4ddc0dcfde3a` | `AUTHORIZED CHANGE` |

The request remains unfiltered and the five-operation MCP allowlist is
unchanged. Focused tests reject pagination, a second data source, a database,
malformed results, and pages parented anywhere else.

## Byte-identical Card 3 files

These other three mission-defined Notion files remain byte-identical:

| File | Source and release SHA-256 | Result |
|---|---|---|
| `app/notion_mcp.py` | `9a0646586f20400feff0ec2c1f2c5c7c5d2ef608296e8d16738a7fb8237085b4` | `IDENTICAL` |
| `app/notion_task_store.py` | `5a45bc20aa479d158ee4324a5b096899952cba8df07c3a27a7c5f9af1012fa17` | `IDENTICAL` |
| `test_notion_adapter.py` | `815ee8eaffba1e49276fcde94ed83a02b818e3d9e36384d00d2c38e280490ced` | `IDENTICAL` |

Two additional Card 3 artifacts were also checked and remain byte-identical:

| File | Source and release SHA-256 | Result |
|---|---|---|
| `test_notion_mcp_discovery.py` | `fc4910584b09a2ed59eaa9d8977ad6e1ef2dbe83db2b2b8cdee0751290b33c37` | `IDENTICAL` |
| `docs/NOTION-SETUP.md` | `b8806479a1601e6274cc1ed0b0ef15dbd1685158f1f18979772deb6e594b0c85` | `IDENTICAL` |

Shared integration files such as `app/chat.py` and `app/task_store.py` are not
claimed byte-identical because this join point integrated later cards.
