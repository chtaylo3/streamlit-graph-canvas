"""Stable diagnostics and public exceptions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A machine-readable failure with an actionable human message."""

    code: str
    message: str
    corrective_action: str
    subject: str | None = None

    def __str__(self) -> str:
        subject = f" [{self.subject}]" if self.subject else ""
        return f"{self.code}{subject}: {self.message} {self.corrective_action}"


class GraphCanvasError(RuntimeError):
    """Base exception for graph canvas failures."""


class ValidationError(GraphCanvasError, ValueError):
    """Raised when schema or graph preflight validation fails."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(str(diagnostic))
