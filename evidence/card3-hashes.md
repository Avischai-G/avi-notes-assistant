# Card 3 byte-identity evidence

Source: Card `4b48fec2`, clone `coroner-card3`. Comparison used both `cmp -s`
and SHA-256 on 2026-08-23. All rows are `IDENTICAL`.

| File | SHA-256 |
|---|---|
| `app/notion_mcp.py` | `9a0646586f20400feff0ec2c1f2c5c7c5d2ef608296e8d16738a7fb8237085b4` |
| `app/notion_task_store.py` | `5a45bc20aa479d158ee4324a5b096899952cba8df07c3a27a7c5f9af1012fa17` |
| `test_notion_adapter.py` | `815ee8eaffba1e49276fcde94ed83a02b818e3d9e36384d00d2c38e280490ced` |
| `test_notion_mcp_discovery.py` | `fc4910584b09a2ed59eaa9d8977ad6e1ef2dbe83db2b2b8cdee0751290b33c37` |
| `scripts/notion_board_setup.py` | `aacfc5eee0cdf408f06cd07b62a79c2a1c8d4237f7e4e61d032af83e0be7ddbf` |
| `docs/NOTION-SETUP.md` | `b8806479a1601e6274cc1ed0b0ef15dbd1685158f1f18979772deb6e594b0c85` |

The first five are the exact executable/test boundary set tracked by Card 9.
The setup document is included as an additional exact comparison. Shared
integration files such as `app/chat.py` and `app/task_store.py` are deliberately
not claimed byte-identical because this join point had to integrate later cards.
