"""Shared test setup. Tests marked `db` need the local Exasol database; they are
skipped (not failed) when it is not reachable. No test calls an AI model."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _exasol_up() -> bool:
    try:
        from app import db
        db.connect(fetch_dict=False).close()
        return True
    except Exception:
        return False


EXASOL = _exasol_up()


def pytest_configure(config):
    config.addinivalue_line("markers", "db: needs the local Exasol database")


def pytest_collection_modifyitems(config, items):
    if EXASOL:
        return
    skip = pytest.mark.skip(reason="Exasol is not reachable on 127.0.0.1:8563")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def worked():
    from app.playground import SCENARIOS
    return {k: SCENARIOS[0][k] for k in ("accounts", "transfers", "request")}
