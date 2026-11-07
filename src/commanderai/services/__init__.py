"""Service layer: all CommanderAI use-cases, free of any console/HTTP concerns.

Each service takes a :class:`~commanderai.services.context.ServiceContext`
(settings + reporter + lazily-loaded card catalog), returns typed results, and
raises :mod:`commanderai.errors` exceptions for user-facing failures. The CLI
and the HTTP API are thin front-ends over these functions.
"""

from commanderai.services.context import ServiceContext

__all__ = ["ServiceContext"]
