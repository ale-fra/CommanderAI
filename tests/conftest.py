"""Tests must not use live external services or an ambient API key."""

import socket

import pytest


@pytest.fixture(autouse=True)
def no_live_services(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Live network access is disabled in tests; mock the service")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
