"""Throwaway (TC-26 AC6): a deliberately failing test to show CI goes red and uploads backend logs. Never merged."""

from harness.backend import BackendProcess


def test_red_ci_demo(backend: BackendProcess) -> None:
    assert backend.handshake.port == -1, "deliberate failure for the TC-26 red-CI demo"
