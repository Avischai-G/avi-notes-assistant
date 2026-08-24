"""Opt-in local-stdio discovery test; it performs no content operation."""

from __future__ import annotations

import os
import unittest

from app.notion_mcp import (
    MCP_TOOL_NAMES,
    STEADY_STATE_OPERATIONS,
    AdkNotionMcpClient,
    NotionConfig,
)


@unittest.skipUnless(
    os.environ.get("RUN_NOTION_MCP_DISCOVERY") == "1",
    "set RUN_NOTION_MCP_DISCOVERY=1 to launch the pinned local MCP child",
)
class ActualDiscoveryTest(unittest.TestCase):
    def test_exact_tools_and_compiled_operations(self):
        config = NotionConfig(
            token="ntn" + "_deliberately_invalid_discovery_probe",
            tasks_database_id="a" * 32,
        )
        with AdkNotionMcpClient(config) as client:
            self.assertEqual(client.discovery.tools, MCP_TOOL_NAMES)
            self.assertEqual(
                client.discovery.operations, frozenset(STEADY_STATE_OPERATIONS)
            )
            self.assertEqual(len(client.discovery.operations), 10)
            self.assertNotIn("create_database", client.discovery.operations)
            self.assertNotIn("create_view", client.discovery.operations)


if __name__ == "__main__":
    unittest.main()
