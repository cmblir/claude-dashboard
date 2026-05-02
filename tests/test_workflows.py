"""Unit tests for deterministic logic in server.workflows.

Covers topological ordering / level grouping (used by the parallel run
executor), the position-only patch fast-path detector, the indexed-field
extractor, and the SQLite runs-table round-trip. Network / subprocess /
SSE behaviour is out of scope here.
"""
from __future__ import annotations

import sqlite3

import pytest

from server import db as db_mod
from server import workflows as wf


@pytest.fixture
def fresh_runs_db(tmp_path, monkeypatch):
    """Redirect server.db at a tmp DB so workflow_runs writes stay isolated."""
    db_file = tmp_path / "wf-runs.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_file)
    monkeypatch.setattr(db_mod, "_INITIALIZED", False)
    # run_history is created by run_center; stub it so _db_init's index DDL
    # has a base table to attach to.
    with sqlite3.connect(str(db_file)) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS run_history "
            "(id INTEGER PRIMARY KEY, source TEXT, item_id TEXT, ts INTEGER)"
        )
    return db_file


def _nodes(*ids):
    return [{"id": i} for i in ids]


def _edges(*pairs):
    return [{"from": a, "to": b} for a, b in pairs]


# ───────── _topological_order / _topological_levels ─────────

class TestTopological:
    def test_linear_chain_levels(self):
        nodes = _nodes("a", "b", "c")
        edges = _edges(("a", "b"), ("b", "c"))
        levels = wf._topological_levels(nodes, edges)
        assert levels == [["a"], ["b"], ["c"]]

    def test_linear_chain_order(self):
        nodes = _nodes("a", "b", "c")
        edges = _edges(("a", "b"), ("b", "c"))
        order = wf._topological_order(nodes, edges)
        assert order == ["a", "b", "c"]

    def test_diamond_groups_parallel_siblings(self):
        # a → b, a → c, b → d, c → d  ⇒  b and c share level 1.
        nodes = _nodes("a", "b", "c", "d")
        edges = _edges(("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"))
        levels = wf._topological_levels(nodes, edges)
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]

    def test_empty_graph(self):
        assert wf._topological_levels([], []) == []
        assert wf._topological_order([], []) == []

    def test_single_isolated_node(self):
        levels = wf._topological_levels(_nodes("solo"), [])
        assert levels == [["solo"]]

    def test_cycle_does_not_raise(self):
        # Kahn's algorithm leaves cycle nodes out of the result silently —
        # we just want to make sure it returns instead of hanging/raising.
        nodes = _nodes("a", "b", "c")
        edges = _edges(("a", "b"), ("b", "c"), ("c", "a"))
        levels = wf._topological_levels(nodes, edges)
        order = wf._topological_order(nodes, edges)
        # All cyclic nodes have nonzero in-degree, so neither emits anything.
        assert levels == []
        assert order == []


# ───────── _is_position_only_patch ─────────

class TestPositionOnlyPatch:
    def test_node_xy_only_is_position_only(self):
        patch = {
            "nodes": [{"id": "a", "x": 1, "y": 2}],
            "viewport": {"panX": 0, "panY": 0, "zoom": 1},
        }
        assert wf._is_position_only_patch(patch) is True

    def test_node_with_data_field_is_not_position_only(self):
        patch = {"nodes": [{"id": "a", "title": "new"}]}
        assert wf._is_position_only_patch(patch) is False

    def test_empty_node_list_is_vacuously_true(self):
        assert wf._is_position_only_patch({"nodes": []}) is True

    def test_empty_dict_is_false(self):
        # Empty patch is not a meaningful position-only update.
        assert wf._is_position_only_patch({}) is False

    def test_unknown_top_level_key_is_false(self):
        assert wf._is_position_only_patch({"name": "foo"}) is False

    def test_viewport_only_is_position_only(self):
        assert wf._is_position_only_patch(
            {"viewport": {"panX": 5, "panY": 10, "zoom": 1.5}}
        ) is True

    def test_non_dict_input_is_false(self):
        assert wf._is_position_only_patch("nope") is False  # type: ignore[arg-type]


# ───────── _run_indexed_fields ─────────

class TestRunIndexedFields:
    def test_extracts_basic_fields(self):
        run = {
            "workflowId": "wf-1",
            "status": "running",
            "startedAt": 1000.0,
            "finishedAt": 2000.0,
            "iteration": 2,
            "repeat": {"maxIterations": 5},
            "costUsd": 0.5,
            "tokensIn": 100,
            "tokensOut": 200,
        }
        wid, status, started, ended, it, total, cost, tin, tout = (
            wf._run_indexed_fields(run)
        )
        assert wid == "wf-1"
        assert status == "running"
        assert started == 1000.0
        assert ended == 2000.0
        assert it == 2
        assert total == 5
        assert cost == 0.5
        assert tin == 100
        assert tout == 200

    def test_handles_missing_fields(self):
        wid, status, started, ended, it, total, cost, tin, tout = (
            wf._run_indexed_fields({})
        )
        assert wid == ""
        assert status == "running"
        assert started == 0.0
        assert ended is None
        assert it == 0
        assert total == 1
        assert cost == 0.0
        assert tin == 0
        assert tout == 0


# ───────── _runs_db_save / load / delete ─────────

class TestRunsDbRoundTrip:
    def test_save_then_load(self, fresh_runs_db):
        run = {
            "id": "run-x",
            "workflowId": "wf-x",
            "status": "ok",
            "startedAt": 1234.0,
            "iteration": 1,
        }
        wf._runs_db_save("run-x", run)
        loaded = wf._runs_db_load(run_id="run-x")
        assert "run-x" in loaded
        assert loaded["run-x"]["workflowId"] == "wf-x"
        assert loaded["run-x"]["status"] == "ok"

    def test_delete_removes_row(self, fresh_runs_db):
        run = {"id": "run-y", "workflowId": "wf-y", "status": "ok",
               "startedAt": 1.0}
        wf._runs_db_save("run-y", run)
        assert "run-y" in wf._runs_db_load(run_id="run-y")
        wf._runs_db_delete("run-y")
        assert "run-y" not in wf._runs_db_load(run_id="run-y")

    def test_save_invalid_run_id_is_noop(self, fresh_runs_db):
        # Empty run_id should not raise nor insert anything.
        wf._runs_db_save("", {"workflowId": "wf-z"})
        # Loading without filter should return an empty dict (no rows).
        assert wf._runs_db_load() == {}


class TestStickyAnnotations:
    """QQ36 / QQ37 / QQ59 / QQ63 — sticky note nodes are a non-executing
    annotation primitive. Make sure they survive sanitize, get filtered
    out of the executor, and orphan edges referencing them are dropped."""

    def test_sanitize_preserves_sticky_fields(self):
        n = wf._sanitize_node({
            "id": "n-stk", "type": "sticky", "x": 100, "y": 50,
            "data": {"text": "## hi", "color": "blue", "width": 240, "height": 120},
        })
        assert n is not None
        assert n["type"] == "sticky"
        assert n["data"]["text"] == "## hi"
        assert n["data"]["color"] == "blue"
        assert n["data"]["width"] == 240
        assert n["data"]["height"] == 120

    def test_sanitize_clamps_invalid_color_and_dimensions(self):
        n = wf._sanitize_node({
            "id": "n-stk2", "type": "sticky", "x": 0, "y": 0,
            "data": {"text": "x", "color": "rainbow", "width": 50, "height": 999999},
        })
        assert n["data"]["color"] == "yellow"  # invalid → default
        assert n["data"]["width"] == 120  # clamped to floor
        assert n["data"]["height"] == 800  # clamped to ceiling

    def test_execute_returns_pass_through(self):
        n = wf._sanitize_node({
            "id": "n-stk3", "type": "sticky", "x": 0, "y": 0,
            "data": {"text": "note", "color": "yellow", "width": 220, "height": 140},
        })
        r = wf._execute_node(n, ["upstream input ignored"])
        assert r["status"] == "ok"
        assert r["output"] == ""
        assert r["sessionId"] == ""

    def test_sanitize_workflow_drops_edges_attached_to_sticky(self):
        clean = wf._sanitize_workflow({
            "name": "test",
            "nodes": [
                {"id": "n-stk", "type": "sticky", "x": 0, "y": 0, "data": {"text": "n", "color": "yellow"}},
                {"id": "n-a", "type": "session", "x": 200, "y": 0, "data": {"subject": "s"}},
                {"id": "n-b", "type": "session", "x": 400, "y": 0, "data": {"subject": "s"}},
            ],
            "edges": [
                {"id": "e1", "from": "n-stk", "fromPort": "out", "to": "n-a", "toPort": "in"},
                {"id": "e2", "from": "n-a",   "fromPort": "out", "to": "n-stk", "toPort": "in"},
                {"id": "e3", "from": "n-a",   "fromPort": "out", "to": "n-b", "toPort": "in"},
            ],
        })
        assert clean is not None
        # All three nodes survive; only the legitimate n-a → n-b edge remains.
        assert len(clean["nodes"]) == 3
        assert len(clean["edges"]) == 1
        assert clean["edges"][0]["from"] == "n-a"
        assert clean["edges"][0]["to"] == "n-b"


    def test_list_api_splits_sticky_from_node_count(self, monkeypatch, tmp_path):
        """QQ79 — api_workflow_list returns nodeCount = (total - sticky) and
        a separate stickyCount field so the sidebar reads
        '5 노드 + 2 🟨' instead of bundling them."""
        # Redirect the workflows store to a temp file so the test is isolated.
        store_file = tmp_path / "wf-q79.json"
        monkeypatch.setattr(wf, "WORKFLOWS_PATH", store_file)
        # Invalidate the in-memory load cache so the patched path is honored.
        with wf._LOAD_CACHE["lock"]:
            wf._LOAD_CACHE["data"] = None
            wf._LOAD_CACHE["mtime"] = 0
        # Build a minimal store with one workflow holding 1 sticky + 2 real.
        wf._dump_all({
            "workflows": {
                "wf-q79": {
                    "id": "wf-q79", "name": "q79-test",
                    "createdAt": 1, "updatedAt": 1,
                    "nodes": [
                        {"id": "n-stk", "type": "sticky", "x": 0, "y": 0, "data": {}},
                        {"id": "n-start", "type": "start", "x": 100, "y": 0, "data": {}},
                        {"id": "n-s", "type": "session", "x": 200, "y": 0, "data": {}},
                    ],
                    "edges": [
                        {"id": "e1", "from": "n-start", "fromPort": "out", "to": "n-s", "toPort": "in"},
                    ],
                },
            },
            "runs": {},
        })
        out = wf.api_workflows_list()
        assert out["ok"] is True
        items = [w for w in out["workflows"] if w["id"] == "wf-q79"]
        assert len(items) == 1
        item = items[0]
        assert item["nodeCount"] == 2  # start + session
        assert item["stickyCount"] == 1
        assert item["edgeCount"] == 1
