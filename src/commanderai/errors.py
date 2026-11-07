"""Domain errors raised by the service layer.

Services never print or exit; they raise one of these. Front-ends translate
them: the CLI prints ``message`` (red) plus each of ``details`` (dim) and exits
with code 1; the HTTP API maps ``status_code``/``code`` to an error response.
"""

from __future__ import annotations

from typing import Any


class CommanderAIError(Exception):
    """Base class for all expected, user-facing failures."""

    code: str = "error"
    status_code: int = 400

    def __init__(self, message: str, *, details: list[str] | None = None, **data: Any):
        super().__init__(message)
        self.message = message
        self.details: list[str] = list(details or [])
        self.data: dict[str, Any] = data

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "data": self.data,
        }


# --- invalid input ------------------------------------------------------------

class InvalidRequestError(CommanderAIError):
    code = "invalid_request"
    status_code = 400


class UnknownThemeError(InvalidRequestError):
    code = "unknown_theme"


class UnknownColorsError(InvalidRequestError):
    code = "unknown_colors"


# --- missing things -------------------------------------------------------------

class NotFoundError(CommanderAIError):
    code = "not_found"
    status_code = 404


class CollectionNotFoundError(NotFoundError):
    code = "collection_not_found"


class CardNotFoundError(NotFoundError):
    code = "card_not_found"


class DeckNotFoundError(NotFoundError):
    code = "deck_not_found"


# --- rules / data problems ---------------------------------------------------------

class UnprocessableError(CommanderAIError):
    code = "unprocessable"
    status_code = 422


class IllegalCommanderError(UnprocessableError):
    code = "illegal_commander"


class IllegalPartnerError(UnprocessableError):
    code = "illegal_partner"


class EmptyCollectionError(UnprocessableError):
    code = "empty_collection"


class CollectionTooSmallError(UnprocessableError):
    code = "collection_too_small"


class InsufficientCardsError(UnprocessableError):
    code = "insufficient_cards"


class NoMatchingCommanderError(UnprocessableError):
    code = "no_matching_commander"


class CommanderNotIdentifiedError(UnprocessableError):
    code = "commander_not_identified"


# --- external services -------------------------------------------------------------

class ServiceUnavailableError(CommanderAIError):
    code = "service_unavailable"
    status_code = 503


class CatalogNotFoundError(NotFoundError):
    code = "catalog_not_found"
    status_code = 503


class LLMError(ServiceUnavailableError):
    """The LLM (Claude) could not be used: missing key, network, bad response."""

    code = "llm_failed"


class ReadOnlyError(InvalidRequestError):
    """The target can't be modified (e.g. a built-in sample collection)."""

    code = "read_only"
    status_code = 409


class GoneError(CommanderAIError):
    """A temporary resource expired (e.g. an unsaved build preview)."""

    code = "gone"
    status_code = 410
