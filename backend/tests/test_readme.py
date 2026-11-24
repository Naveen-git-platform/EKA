"""Keeps the README honest: measured numbers match the committed benchmark and every local link/image exists."""
from __future__ import annotations

import json
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
README = (REPO / "README.md").read_text(encoding="utf-8")


def test_readme_numbers_match_committed_benchmark():
    bench = json.loads((BACKEND / "docs" / "benchmark_results.json").read_text(encoding="utf-8"))
    default = bench["results"]["hybrid (weighted 0.7) [default]"]["all"]
    vec = bench["results"]["vector only"]["all"]
    bm25 = bench["results"]["BM25 only"]["all"]
    assert f"{default['recall@3']:.2f} / {default['mrr@3']:.2f}" in README
    assert f"{vec['recall@3']:.2f} / {vec['mrr@3']:.2f}" in README
    assert f"{bm25['recall@3']:.2f} / {bm25['mrr@3']:.2f}" in README
    assert f"{bench['n_questions']} labelled" in README and f"{bench['n_chunks']} chunks" in README


def test_readme_local_links_and_images_exist():
    targets = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", README)
    local = [t for t in targets if not re.match(r"^[a-z]+://", t) and not t.startswith("mailto:")]
    assert local, "expected relative links in the README"
    missing = [t for t in local if not (REPO / t).exists()]
    assert not missing, missing


def test_readme_documents_every_route_the_api_exposes():
    from app.core.config import Settings
    from app.main import create_app

    paths = set(create_app(Settings(_env_file=None, llm_provider="fake")).openapi()["paths"])
    for path in paths:
        needle = re.sub(r"\{[^}]+\}", "{id}", path)
        if needle.startswith("/evaluations/runs"):
            needle = "/evaluations/runs"
        assert needle in README or path.split("/{")[0] in README, f"{path} is not mentioned in the README"


def test_readme_points_at_the_right_commands_and_ports():
    assert "docker compose up --build" in README
    assert "localhost:3000" in README and "localhost:8000" in README
    assert "backend/.env.example" in README
    assert "streamlit" not in README.lower()
