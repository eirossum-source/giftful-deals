import re
from pathlib import Path

import pytest

from error_log import ErrorLog


def test_log_error_appends_iso_timestamped_line(tmp_path: Path):
    log_file = tmp_path / "errors.log"
    log = ErrorLog(log_file)

    log.error("price unavailable for https://shop.example.com/x")

    content = log_file.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert len(lines) == 1
    assert re.match(
        r"^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\] "
        r"price unavailable for https://shop\.example\.com/x$",
        lines[0],
    ), lines[0]


def test_multiple_errors_append_not_overwrite(tmp_path: Path):
    log = ErrorLog(tmp_path / "errors.log")
    log.error("first")
    log.error("second")

    content = (tmp_path / "errors.log").read_text(encoding="utf-8")
    assert content.count("first") == 1
    assert content.count("second") == 1
    assert content.strip().splitlines()[-1].endswith("second")


def test_error_count_exposed(tmp_path: Path):
    log = ErrorLog(tmp_path / "errors.log")
    assert log.count == 0
    log.error("a")
    log.error("b")
    assert log.count == 2
