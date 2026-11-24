"""Guards the files users copy/paste or build from: .env.example, docker-compose.yml, Dockerfiles, CI workflow."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def env_example_keys() -> list[str]:
    keys = []
    for line in (BACKEND / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line.split("=", 1)[0])
    return keys


def compose() -> dict:
    return yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))


def test_env_example_documents_the_real_defaults(monkeypatch):
    """.env.example must parse, name only real settings, and mirror the code defaults (no doc drift)."""
    for key in env_example_keys():
        monkeypatch.delenv(key, raising=False)
    from_file = Settings(_env_file=BACKEND / ".env.example")
    defaults = Settings(_env_file=None)
    assert from_file.model_dump() == defaults.model_dump()
    fields = {name.upper() for name in Settings.model_fields}
    assert set(env_example_keys()) <= fields, set(env_example_keys()) - fields


def test_env_example_has_no_inline_comments_that_break_compose_env_files():
    for line in (BACKEND / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            assert " #" not in line, f"inline comment would end up in the value: {line!r}"


def test_compose_stack_wiring():
    cfg = compose()
    svc = cfg["services"]
    assert set(svc) == {"qdrant", "backend", "web"}
    assert svc["backend"]["environment"]["QDRANT_URL"] == "http://qdrant:6333"
    assert svc["backend"]["depends_on"]["qdrant"]["condition"] == "service_healthy"
    assert svc["web"]["depends_on"]["backend"]["condition"] == "service_healthy"
    assert "8000:8000" in svc["backend"]["ports"] and "3000:3000" in svc["web"]["ports"]
    assert "healthcheck" in svc["qdrant"]
    assert {"qdrant_data", "eka_data"} <= set(cfg["volumes"])
    assert svc["backend"]["environment"]["DATA_DIR"] == "/data"  # overrides DATA_DIR from .env
    for name in ("backend", "web"):  # build contexts reference files that exist
        build = svc[name]["build"]
        assert (REPO / build["context"] / build["dockerfile"]).exists()


def test_web_receives_a_browser_reachable_api_url():
    """The browser, not the compose network, calls the API, so the build arg must be a host-published address."""
    arg = compose()["services"]["web"]["build"]["args"]["NEXT_PUBLIC_API_URL"]
    assert "localhost:8000" in arg and "backend" not in arg


def test_qdrant_server_version_is_compatible_with_client():
    """Qdrant supports a client/server skew of at most one minor version."""
    from importlib.metadata import version

    image = compose()["services"]["qdrant"]["image"]
    server = re.search(r"v(\d+)\.(\d+)", image)
    client_major, client_minor = (int(x) for x in version("qdrant-client").split(".")[:2])
    assert int(server.group(1)) == client_major
    assert abs(int(server.group(2)) - client_minor) <= 1, "qdrant-client and server minor versions drifted apart"


def test_backend_dockerfile_is_unprivileged_cpu_only_and_has_what_it_serves():
    text = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "USER eka" in text and "HEALTHCHECK" in text and "EXPOSE 8000" in text
    assert "download.pytorch.org/whl/cpu" in text and "all-MiniLM-L6-v2" in text
    for needed in ("data/sample_docs", "data/eval", "docs/benchmark_results.json"):
        assert f"COPY {needed}" in text
        assert (BACKEND / needed).exists(), f"{needed} is copied into the image but missing"


def test_web_dockerfile_builds_a_standalone_unprivileged_server():
    text = (REPO / "web" / "Dockerfile").read_text(encoding="utf-8")
    assert "USER node" in text and "HEALTHCHECK" in text and "EXPOSE 3000" in text
    assert ".next/standalone" in text and "pnpm install --frozen-lockfile" in text
    assert "NEXT_PUBLIC_API_URL" in text
    assert "output: \"standalone\"" in (REPO / "web" / "next.config.ts").read_text(encoding="utf-8")


def test_constraints_file_is_used_by_docker_and_consistent_with_requirements():
    constraints = (BACKEND / "constraints.txt").read_text(encoding="utf-8").lower()
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "-c constraints.txt" in dockerfile and "COPY requirements.txt constraints.txt" in dockerfile
    # every direct dependency is pinned in the constraints (torch is installed separately from the CPU index)
    for line in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=\[]", line, maxsplit=1)[0].strip().lower().replace("_", "-")
        if name == "torch":
            continue
        assert re.search(rf"^{re.escape(name)}==", constraints.replace("_", "-"), re.M), f"{name} not pinned"


def test_ci_workflow_runs_every_check_the_project_documents():
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    jobs = ci["jobs"]
    assert set(jobs) == {"backend", "web", "docker"}
    backend = " ".join(s.get("run", "") for s in jobs["backend"]["steps"])
    assert "ruff check" in backend and "pytest" in backend and "constraints.txt" in backend
    web = " ".join(s.get("run", "") for s in jobs["web"]["steps"])
    for cmd in ("pnpm lint", "pnpm typecheck", "pnpm test", "pnpm build", "--frozen-lockfile"):
        assert cmd in web, cmd
    triggers = ci.get("on") or ci.get(True)  # YAML 1.1 parses a bare `on` key as the boolean True
    assert "pull_request" in triggers


def test_streamlit_is_gone():
    assert "streamlit" not in (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
    assert not (REPO / "frontend").exists()
