"""HTTP API (FastAPI) over the service layer, plus static serving of the web UI.

Requires the optional ``web`` extra: ``pip install -e '.[web]'``.
"""

from commanderai.api.app import create_app

__all__ = ["create_app"]
