from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location("export_graph", ROOT / "scripts" / "export_graph.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_render_contains_mermaid_with_all_nodes():
    text = _load_script().render()
    assert "```mermaid" in text and "graph TD" in text
    for node in ("planner", "retriever", "critic", "answer"):
        assert node in text


def test_committed_doc_is_up_to_date():
    """If this fails, run: python scripts/export_graph.py"""
    doc = (ROOT / "docs" / "agent_graph.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert doc == _load_script().render().replace("\r\n", "\n")
