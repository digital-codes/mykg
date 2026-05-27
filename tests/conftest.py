import os
from pathlib import Path

import pytest


def _load_key(env_var: str) -> str | None:
    key = os.environ.get(env_var, "").strip()
    if not key:
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith(env_var + "="):
                    key = line.partition("=")[2].strip()
                    break
    return key or None


@pytest.fixture(scope="session")
def openrouter_api_key():
    key = _load_key("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set")
    return key


@pytest.fixture(scope="session")
def live_corpus(tmp_path_factory):
    d = tmp_path_factory.mktemp("corpus")
    (d / "people.md").write_text(
        "Alice is a software engineer at Acme Corp. "
        "Bob manages the infrastructure team at Acme Corp."
    )
    (d / "projects.md").write_text(
        "Acme Corp is building a distributed database called Prometheus. "
        "Alice leads the Prometheus project."
    )
    (d / "history.md").write_text(
        "Acme Corp was founded in 2010. Bob joined in 2015 and Alice in 2018."
    )
    return d
