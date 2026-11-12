"""Guardrail: production must install exactly what uv.lock pins.

`pip install -e .` resolves fresh from the pyproject ranges at every build, so
the dependency set that was audited (uv.lock) is not what runs. The build must
install from the lock, fail if the lock is stale, and the server must run from
that environment.
"""

from pathlib import Path

RENDER_YAML = (Path(__file__).resolve().parent.parent / "render.yaml").read_text()


def _command(key: str) -> str:
    for line in RENDER_YAML.splitlines():
        if line.strip().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"{key} not found in render.yaml")


def test_build_installs_from_lockfile_and_fails_if_stale():
    build = _command("buildCommand")
    assert "uv sync --locked" in build, build
    assert "--no-dev" in build, build


def test_build_never_resolves_from_pyproject_ranges():
    assert "pip install -e" not in _command("buildCommand")


def test_start_runs_from_the_locked_environment():
    assert _command("startCommand").startswith(".venv/bin/python -m shopify_meta.server_http")
