"""Offline contract tests for the existing-database Notion MCP adapter."""

from __future__ import annotations

import asyncio
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.notion_mcp import (
    MCP_TOOL_NAMES,
    STEADY_STATE_OPERATIONS,
    AdkNotionMcpClient,
    McpDiscovery,
    NotionConfig,
    NotionConfigurationError,
    NotionMcpError,
    _redact,
    _RedactingPipe,
    _stdio_child_spec,
)
from app.notion_task_store import (
    DONE,
    IN_PROGRESS,
    MINUTES,
    NAME,
    NOT_STARTED,
    NOTES,
    PLACE,
    STATUS,
    WHEN,
    NotionTaskStore,
)
from scripts import notion_board_setup as setup
from scripts.notion_board_setup import (
    _read_env,
    _validate_isolation_result,
)

TOKEN = "ntn" + "_offline_test_value"
DATABASE_ID = "a" * 32


def steady_env() -> dict[str, str]:
    return {
        "NOTION_TOKEN": TOKEN,
        "NOTION_TASKS_DATABASE_ID": DATABASE_ID,
    }


class FakeMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.pages: dict[str, dict] = {}
        self._counter = 0
        self.closed = False
        self.discovery = McpDiscovery(
            tools=MCP_TOOL_NAMES,
            operations=frozenset(STEADY_STATE_OPERATIONS),
        )

    @staticmethod
    def _flatten(properties: dict) -> dict:
        result: dict = {}
        for name, value in properties.items():
            if name == NAME:
                continue
            if "status" in value:
                result[name] = value["status"]["name"]
            elif "date" in value:
                result[name] = value["date"]["start"]
            elif "select" in value:
                result[name] = value["select"]["name"]
            elif "number" in value:
                result[name] = value["number"]
            elif "rich_text" in value:
                result[name] = "".join(
                    item["text"]["content"] for item in value["rich_text"]
                )
        return result

    def execute(self, operation: str, payload: dict):
        self.calls.append((operation, payload))
        if operation == "create_page":
            self._counter += 1
            page_id = f"page-{self._counter}"
            properties = payload["properties"]
            title = properties[NAME]["title"][0]["text"]["content"]
            self.pages[page_id] = {
                "id": page_id,
                "title": title,
                "properties": self._flatten(properties),
            }
            return {"id": page_id, "title": title}
        if operation == "set_page_title":
            self.pages[payload["page_id"]]["title"] = payload["title"]
            return {"id": payload["page_id"]}
        if operation == "set_page_property":
            value = payload["value"]
            self.pages[payload["page_id"]]["properties"][payload["name"]] = value[
                "status"
            ]["name"]
            return {"id": payload["page_id"]}
        if operation == "query_database":
            rows = list(self.pages.values())
            selected = payload.get("filter", {}).get("status", {}).get("equals")
            if selected:
                rows = [row for row in rows if row["properties"][STATUS] == selected]
            return {"results": [dict(row) for row in rows], "truncated": False}
        if operation == "archive_page":
            del self.pages[payload["page_id"]]
            return {"id": payload["page_id"], "in_trash": True}
        raise AssertionError(f"unexpected operation: {operation}")

    def close(self) -> None:
        self.closed = True


class ConfigurationTests(unittest.TestCase):
    def test_requires_only_token_and_tasks_database_id(self):
        config = NotionConfig.from_env(steady_env())
        self.assertEqual(config.allowed_operations, ",".join(STEADY_STATE_OPERATIONS))
        self.assertNotIn(TOKEN, repr(config))
        self.assertNotIn(DATABASE_ID, repr(config))

        for missing in steady_env():
            values = steady_env()
            del values[missing]
            with self.assertRaises(NotionConfigurationError):
                NotionConfig.from_env(values)

    def test_allowlist_is_compiled_and_contains_no_schema_or_view_mutation(self):
        self.assertEqual(
            STEADY_STATE_OPERATIONS,
            (
                "create_page",
                "set_page_title",
                "set_page_property",
                "query_database",
                "archive_page",
                "restore_page",
                "get_page_markdown",
                "update_page_markdown",
                "add_page_comment",
                "list_comments",
            ),
        )
        forbidden = {
            "create_database",
            "update_database",
            "create_view",
            "update_view",
            "search_pages",
        }
        self.assertTrue(forbidden.isdisjoint(STEADY_STATE_OPERATIONS))

    def test_token_and_database_id_are_redacted(self):
        value = f"failure for {TOKEN} and {DATABASE_ID}"
        redacted = _redact(value, TOKEN, DATABASE_ID)
        self.assertNotIn(TOKEN, redacted)
        self.assertNotIn(DATABASE_ID, redacted)

        target = io.StringIO()
        pipe = _RedactingPipe(target, TOKEN, DATABASE_ID)
        os.write(pipe.fileno(), f"child logged {TOKEN} {DATABASE_ID}\n".encode())
        pipe.close()
        self.assertNotIn(TOKEN, target.getvalue())
        self.assertNotIn(DATABASE_ID, target.getvalue())

    def test_secrets_are_only_in_child_environment(self):
        config = NotionConfig.from_env(steady_env())
        spec = _stdio_child_spec(config, Path("/app"), "/usr/local/bin/npx")
        self.assertNotIn(TOKEN, spec.command)
        self.assertTrue(all(TOKEN not in arg for arg in spec.args))
        self.assertTrue(all(DATABASE_ID not in arg for arg in spec.args))
        self.assertEqual(
            spec.args,
            ("--yes", "--offline", "notion-mcp-server@2.13.0"),
        )
        self.assertEqual(spec.env["NOTION_TOKEN"], TOKEN)
        self.assertNotIn(DATABASE_ID, spec.env.values())
        self.assertEqual(
            spec.env["NOTION_ALLOWED_OPERATIONS"],
            ",".join(STEADY_STATE_OPERATIONS),
        )
        self.assertNotIn(TOKEN, repr(spec))


class McpEnvelopeTests(unittest.TestCase):
    class _Result:
        def __init__(self, wire: dict):
            self.wire = wire

        def model_dump(self, **_):
            return self.wire

    class _Session:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error
            self.calls = 0

        async def call_tool(self, *_args, **_kwargs):
            self.calls += 1
            if self.error:
                raise self.error
            return self.result

    class _Manager:
        def __init__(self, session):
            self.session = session

        async def create_session(self):
            return self.session

    def _client(self, session):
        client = AdkNotionMcpClient.__new__(AdkNotionMcpClient)
        client._config = NotionConfig.from_env(steady_env())
        client._discovery = McpDiscovery(
            tools=MCP_TOOL_NAMES,
            operations=frozenset(STEADY_STATE_OPERATIONS),
        )
        client._toolset = type(
            "FakeToolset",
            (),
            {"_mcp_session_manager": self._Manager(session)},
        )()
        client._timeout_seconds = 1.0
        return client

    def test_success_envelope_is_parsed(self):
        result = self._Result(
            {"content": [{"type": "text", "text": '{"ok":true,"data":{}}'}]}
        )
        session = self._Session(result=result)
        data = asyncio.run(self._client(session)._execute("query_database", {}))
        self.assertEqual(data, {})
        self.assertEqual(session.calls, 1)

    def test_transport_error_is_not_retried(self):
        session = self._Session(error=ConnectionError("connection dropped"))
        with self.assertRaisesRegex(NotionMcpError, "transport failed"):
            asyncio.run(self._client(session)._execute("create_page", {}))
        self.assertEqual(session.calls, 1)


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.config = NotionConfig.from_env(steady_env())
        self.client = FakeMcpClient()
        self.store = NotionTaskStore(self.config, self.client)

    def test_a_board_without_a_notes_column_still_works(self):
        """Avi's live board has no Notes column, and every turn searched it.

        Notion rejects the whole request when a filter or a write names a
        property the database does not have, so search_tasks failed on every
        prompt. The store reads the column set off a row and leaves Notes out.
        """
        self.store.create_task("Existing row", place="Office")
        for page in self.client.pages.values():
            page["properties"].pop(NOTES, None)  # a board edited by hand
        self.store._columns = None  # a fresh process, learning from scratch

        self.assertFalse(self.store.has_column(NOTES))
        self.store.search_tasks("passport")
        operation, payload = self.client.calls[-1]
        self.assertEqual(operation, "query_database")
        self.assertEqual(payload["filter"], {"property": NAME, "title": {"contains": "passport"}})

        self.store.create_task("Second row", notes="dropped rather than rejected")
        _, created = self.client.calls[-1]
        self.assertNotIn(NOTES, created["properties"])

    def test_an_unreadable_board_keeps_notes_rather_than_dropping_them(self):
        """An empty board teaches nothing; assume the column is there."""
        self.assertTrue(self.store.has_column(NOTES))
        self.store.create_task("First ever", notes="Avi's words")
        _, created = self.client.calls[-1]
        self.assertIn(NOTES, created["properties"])

    def test_create_maps_all_six_properties_and_allows_new_place(self):
        task = self.store.create_task(
            "  Remember passport  ",
            IN_PROGRESS,
            when="2030-04-05T09:30:00+03:00",
            place="Airport",
            minutes=12.5,
            notes="Bring the blue folder",
        )
        self.assertEqual(task.title, "Remember passport")
        self.assertEqual(task.status, IN_PROGRESS)
        self.assertEqual(task.place, "Airport")
        operation, payload = self.client.calls[-1]
        self.assertEqual(operation, "create_page")
        self.assertEqual(
            payload["parent"],
            {"type": "database_id", "database_id": DATABASE_ID},
        )
        properties = payload["properties"]
        self.assertEqual(set(properties), {NAME, STATUS, WHEN, PLACE, MINUTES, NOTES})
        self.assertEqual(properties[STATUS], {"status": {"name": IN_PROGRESS}})
        self.assertEqual(properties[WHEN]["date"]["start"], task.when)
        self.assertEqual(properties[PLACE], {"select": {"name": "Airport"}})
        self.assertEqual(properties[MINUTES], {"number": 12.5})
        self.assertEqual(
            properties[NOTES]["rich_text"][0]["text"]["content"], task.notes
        )

    def test_default_status_rename_move_and_queries_are_database_scoped(self):
        created = self.store.create_task("Synthetic")
        self.assertEqual(created.status, NOT_STARTED)
        renamed = self.store.rename_task(created.id, "Renamed synthetic")
        moved = self.store.move_task(created.id, DONE)
        self.assertEqual(renamed.title, "Renamed synthetic")
        self.assertEqual(moved.status, DONE)
        self.assertEqual(self.store.list_tasks(NOT_STARTED), [])
        self.assertEqual(
            [task.id for task in self.store.list_tasks(DONE)], [created.id]
        )
        mutated_ids = {
            payload["page_id"]
            for operation, payload in self.client.calls
            if operation in {"set_page_title", "set_page_property"}
        }
        self.assertEqual(mutated_ids, {created.id})

    def test_unknown_task_never_reaches_a_mutating_operation(self):
        with self.assertRaisesRegex(ValueError, "configured Notion database"):
            self.store.rename_task("outside-page", "Do not touch")
        self.assertEqual(
            [operation for operation, _ in self.client.calls], ["query_database"]
        )

    def test_invalid_values_never_reach_mcp(self):
        invalid = (
            lambda: self.store.create_task("x", "Blocked"),
            lambda: self.store.create_task("x", when="next Tuesday"),
            lambda: self.store.create_task("x", minutes=-1),
            lambda: self.store.create_task("   "),
        )
        for call in invalid:
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(self.client.calls, [])


class IsolationTests(unittest.TestCase):
    def test_requires_exactly_one_matching_database_and_no_more_pages(self):
        good = {
            "results": [
                {
                    "object": "data_source",
                    "id": "b" * 32,
                    "parent": {"type": "database_id", "database_id": DATABASE_ID},
                }
            ],
            "has_more": False,
        }
        _validate_isolation_result(good, DATABASE_ID)

        bad_values = (
            {"results": [], "has_more": False},
            {"results": good["results"] * 2, "has_more": False},
            {"results": good["results"], "has_more": True},
            {
                "results": [
                    {
                        "object": "data_source",
                        "id": "b" * 32,
                        "parent": {
                            "type": "database_id",
                            "database_id": "c" * 32,
                        },
                    }
                ],
                "has_more": False,
            },
            {
                "results": [
                    {
                        "object": "database",
                        "id": DATABASE_ID,
                        "parent": {"type": "workspace", "workspace": True},
                    }
                ],
                "has_more": False,
            },
        )
        for bad in bad_values:
            with self.assertRaises(RuntimeError):
                _validate_isolation_result(bad, DATABASE_ID)


class SecretFileTests(unittest.TestCase):
    def test_secret_file_requires_exact_two_keys_and_mode_0600(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notion.env"
            path.write_text(
                f"NOTION_TOKEN={TOKEN}\nNOTION_TASKS_DATABASE_ID={DATABASE_ID}\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
            self.assertEqual(_read_env(path), steady_env())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            path.write_text(path.read_text() + "NOTION_ALLOWED_OPERATIONS=read\n")
            with self.assertRaisesRegex(RuntimeError, "exactly"):
                _read_env(path)


class LiveSmokeWorkflowTests(unittest.TestCase):
    def _run(self, pages: dict[str, dict], marker: str | None = None):
        client = FakeMcpClient()
        client.pages.update(pages)
        store = NotionTaskStore(NotionConfig.from_env(steady_env()), client)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        state_path = Path(temp.name) / "state.json"
        if marker:
            setup._write_smoke_state(marker, state_path)
        with (
            patch.object(setup, "_read_env", return_value=steady_env()),
            patch.object(setup, "NotionTaskStore", return_value=store),
        ):
            setup.live_smoke(True, state_path)
        return client, state_path

    def test_fresh_smoke_archives_every_created_row_and_ends_empty(self):
        client, state_path = self._run({})
        operations = [operation for operation, _ in client.calls]
        self.assertEqual(operations.count("create_page"), 2)
        self.assertEqual(operations.count("archive_page"), 2)
        self.assertIn("set_page_title", operations)
        self.assertIn("set_page_property", operations)
        self.assertEqual(client.pages, {})
        self.assertFalse(state_path.exists())

    def test_interrupted_smoke_resumes_owned_rows_without_recreating(self):
        marker = "card3-" + "1" * 32
        pages = {
            "fields": {
                "id": "fields",
                "title": f"{marker} six-property mapping",
                "properties": {
                    STATUS: NOT_STARTED,
                    WHEN: "2099-01-01",
                    PLACE: "Anywhere",
                    MINUTES: 5,
                    NOTES: f"{marker} temporary smoke row",
                },
            },
            "moving": {
                "id": "moving",
                "title": f"{marker} status move",
                "properties": {STATUS: IN_PROGRESS},
            },
        }
        client, state_path = self._run(pages, marker)
        operations = [operation for operation, _ in client.calls]
        self.assertNotIn("create_page", operations)
        self.assertEqual(operations.count("archive_page"), 2)
        self.assertEqual(client.pages, {})
        self.assertFalse(state_path.exists())

    def test_non_smoke_row_is_never_archived(self):
        client = FakeMcpClient()
        client.pages["personal"] = {
            "id": "personal",
            "title": "Personal row",
            "properties": {STATUS: NOT_STARTED},
        }
        store = NotionTaskStore(NotionConfig.from_env(steady_env()), client)
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            with (
                patch.object(setup, "_read_env", return_value=steady_env()),
                patch.object(setup, "NotionTaskStore", return_value=store),
            ):
                with self.assertRaisesRegex(RuntimeError, "zero rows"):
                    setup.live_smoke(True, state_path)
        self.assertNotIn("archive_page", [operation for operation, _ in client.calls])
        self.assertIn("personal", client.pages)


class ArtifactTests(unittest.TestCase):
    def test_lockfile_pins_expected_package_and_integrity(self):
        lock = json.loads((Path(__file__).parent / "package-lock.json").read_text())
        package = lock["packages"]["node_modules/notion-mcp-server"]
        self.assertEqual(package["version"], "2.13.0")
        self.assertEqual(
            package["integrity"],
            "sha512-+gIJpPu3HwENi1l6eEt6E79J0trZ4lDHkPl47eifoPDFiv4HnJV4nsHXXWiR/fTHl5Er0pu+pgPN6T18FqHhmA==",
        )

    def test_fake_store_is_rejected_in_production(self):
        from app import chat

        with patch.dict(
            os.environ,
            {"TASK_STORE_MODE": "fake", "K_SERVICE": "agent-task-organiser"},
            clear=False,
        ):
            with self.assertRaisesRegex(NotionConfigurationError, "local/offline"):
                chat.init_chat_stores(use_firestore=False)
            with self.assertRaisesRegex(RuntimeError, "not initialized"):
                chat.get_stores()


if __name__ == "__main__":
    unittest.main()
