"""Guards the files users copy/paste or build from: .env.example, docker-compose.yml, Dockerfiles, README facts."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def env_example_keys() -> list[str]:
    keys = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line.split("=", 1)[0])
    return keys


def test_env_example_documents_the_real_defaults(monkeypatch):
    """.env.example must parse, name only real settings, and mirror the code defaults (no doc drift)."""
    for key in env_example_keys():
        monkeypatch.delenv(key, raising=False)
    from_file = Settings(_env_file=ROOT / ".env.example")
    defaults = Settings(_env_file=None)
    assert from_file.model_dump() == defaults.model_dump()
    fields = {name.upper() for name in Settings.model_fields}
    assert set(env_example_keys()) <= fields, set(env_example_keys()) - fields


def test_env_example_has_no_inline_comments_that_break_compose_env_files():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            assert " #" not in line, f"inline comment would end up in the value: {line!r}"


def test_compose_stack_wiring():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    svc = compose["services"]
    assert set(svc) == {"qdrant", "backend", "frontend"}
    assert svc["backend"]["environment"]["QDRANT_URL"] == "http://qdrant:6333"
    assert svc["backend"]["depends_on"]["qdrant"]["condition"] == "service_healthy"
    assert svc["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"
    assert svc["frontend"]["environment"]["BACKEND_URL"] == "http://backend:8000"
    assert "8000:8000" in svc["backend"]["ports"] and "8501:8501" in svc["frontend"]["ports"]
    assert "healthcheck" in svc["qdrant"]
    assert {"qdrant_data", "eka_data"} <= set(compose["volumes"])
    assert svc["backend"]["environment"]["DATA_DIR"] == "/data"  # overrides DATA_DIR from .env
    for name in ("backend", "frontend"):  # build contexts reference files that exist
        assert (ROOT / svc[name]["build"]["dockerfile"]).exists()


def test_qdrant_server_version_is_compatible_with_client():
    """Qdrant supports a client/server skew of at most one minor version."""
    from importlib.metadata import version

    image = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]["qdrant"]["image"]
    server = re.search(r"v(\d+)\.(\d+)", image)
    client_major, client_minor = (int(x) for x in version("qdrant-client").split(".")[:2])
    assert int(server.group(1)) == client_major
    assert abs(int(server.group(2)) - client_minor) <= 1, "qdrant-client and server minor versions drifted apart"


def test_dockerfiles_run_unprivileged_and_have_healthchecks():
    for name, port in (("Dockerfile.backend", "8000"), ("Dockerfile.frontend", "8501")):
        text = (ROOT / "docker" / name).read_text(encoding="utf-8")
        assert "USER eka" in text and "HEALTHCHECK" in text and f"EXPOSE {port}" in text
    backend = (ROOT / "docker" / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "download.pytorch.org/whl/cpu" in backend and "all-MiniLM-L6-v2" in backend
    assert "COPY data/sample_docs" in backend and "COPY data/eval" in backend


def test_streamlit_upload_limit_matches_backend_default():
    cfg = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert f"maxUploadSize = {Settings(_env_file=None).max_upload_mb}" in cfg


def test_frontend_requirements_are_standalone():
    reqs = (ROOT / "frontend" / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "streamlit" in reqs and "httpx" in reqs and "torch" not in reqs
    # the frontend image must not need the backend package
    for path in (ROOT / "frontend").glob("*.py"):
        assert not re.search(r"^\s*(from|import)\s+app(\.|\s)", path.read_text(encoding="utf-8"), re.M), path.name


def test_readme_numbers_match_committed_benchmark():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    bench = json.loads((ROOT / "docs" / "benchmark_results.json").read_text(encoding="utf-8"))
    default = bench["results"]["hybrid (weighted 0.7) [default]"]["all"]
    vec = bench["results"]["vector only"]["all"]
    bm25 = bench["results"]["BM25 only"]["all"]
    assert f"{default['recall@3']:.2f} / {default['mrr@3']:.2f}" in readme
    assert f"{vec['recall@3']:.2f} / {vec['mrr@3']:.2f}" in readme
    assert f"{bm25['recall@3']:.2f} / {bm25['mrr@3']:.2f}" in readme
    assert f"{bench['n_questions']} labelled" in readme and f"{bench['n_chunks']} chunks" in readme


def test_constraints_file_is_used_by_docker_and_consistent_with_requirements():
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8").lower()
    backend = (ROOT / "docker" / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "-c constraints.txt" in backend and "COPY requirements.txt constraints.txt" in backend
    # every direct dependency is pinned in the constraints (torch is installed separately from the CPU index)
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=\[]", line, maxsplit=1)[0].strip().lower().replace("_", "-")
        if name == "torch":
            continue
        assert re.search(rf"^{re.escape(name)}==", constraints.replace("_", "-"), re.M), f"{name} not pinned"
