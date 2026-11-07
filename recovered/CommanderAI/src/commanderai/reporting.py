"""Structured progress + notice reporting for the service layer.

Services describe what happens through a :class:`Reporter` instead of printing:

- ``reporter.notice(level, code, message, **data)`` — a user-facing message with a
  stable ``code`` and machine-readable ``data`` (the UI can render it richly; the
  CLI maps each code back to its original console formatting).
- ``with reporter.progress("Loading card database..."):`` — a long-running step
  (the CLI shows a spinner; other reporters ignore it or log it).

Every notice is also recorded in ``reporter.notices`` so results can carry the
full build log.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any

from pydantic import Field

from commanderai.models import PublicModel


class Level(str, Enum):
    INFO = "info"        # neutral information
    DETAIL = "detail"    # secondary / verbose information (dim in the CLI)
    SUCCESS = "success"  # something good happened (green)
    WARNING = "warning"  # degraded result the user should know about (yellow)
    ERROR = "error"      # a problem that did not abort the operation (red)


class Notice(PublicModel):
    level: Level
    code: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class Reporter:
    """Base reporter: records notices, ignores progress. Subclass to display."""

    def __init__(self) -> None:
        self.notices: list[Notice] = []

    def notice(self, level: Level | str, code: str, message: str, /, **data: Any) -> Notice:
        n = Notice(level=Level(level), code=code, message=message, data=data)
        self.notices.append(n)
        self.emit(n)
        return n

    # convenience wrappers
    def info(self, code: str, message: str, /, **data: Any) -> Notice:
        return self.notice(Level.INFO, code, message, **data)

    def detail(self, code: str, message: str, /, **data: Any) -> Notice:
        return self.notice(Level.DETAIL, code, message, **data)

    def success(self, code: str, message: str, /, **data: Any) -> Notice:
        return self.notice(Level.SUCCESS, code, message, **data)

    def warning(self, code: str, message: str, /, **data: Any) -> Notice:
        return self.notice(Level.WARNING, code, message, **data)

    def error(self, code: str, message: str, /, **data: Any) -> Notice:
        return self.notice(Level.ERROR, code, message, **data)

    def emit(self, notice: Notice) -> None:
        """Hook for subclasses to display a notice as soon as it is reported."""

    @contextmanager
    def progress(self, description: str) -> Iterator[None]:
        yield


class CollectingReporter(Reporter):
    """Records notices (and progress step names) without displaying anything."""

    def __init__(self) -> None:
        super().__init__()
        self.steps: list[str] = []

    @contextmanager
    def progress(self, description: str) -> Iterator[None]:
        self.steps.append(description)
        yield
