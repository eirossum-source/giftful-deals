from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def read_fixture(fixtures_dir):
    def _read(name: str) -> str:
        return (fixtures_dir / name).read_text(encoding="utf-8")

    return _read
