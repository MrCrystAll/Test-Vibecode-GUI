# SPDX-License-Identifier: Apache-2.0
"""Self-tests for tools/agent/as_app.py (TC-49). No network and no real keys: GitHub is faked."""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from types import ModuleType
from unittest import mock

TOOLS = Path(__file__).resolve().parents[2]

FAKE_TOKEN = "ghs_FAKE_INSTALLATION_TOKEN_0123456789"
FAKE_KEY = "-----BEGIN PRIVATE KEY-----\nFAKE-KEY-MATERIAL-abcdef\n-----END PRIVATE KEY-----\n"
APP = {"slug": "rlgym-studio-dev-a", "app_id": 1, "installation_id": 2, "bot_user_id": 3}


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


as_app = _load("as_app", TOOLS / "agent" / "as_app.py")


class KeyChoiceTest(unittest.TestCase):
    def choose(self, *names: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in names:
                (folder / name).write_text("not a real key")
            return as_app.key_path("rlgym-studio-dev-a", folder).name

    def test_newest_date_wins_whatever_the_creation_order(self) -> None:
        names = [
            "rlgym-studio-dev-a.2026-11-03.private-key.pem",
            "rlgym-studio-dev-a.2027-01-15.private-key.pem",
            "rlgym-studio-dev-a.2026-12-31.private-key.pem",
        ]
        for order in (names, list(reversed(names))):
            with self.subTest(order=order):
                self.assertEqual(self.choose(*order), "rlgym-studio-dev-a.2027-01-15.private-key.pem")

    def test_dated_beats_undated(self) -> None:
        chosen = self.choose(
            "rlgym-studio-dev-a.zzz.pem",
            "rlgym-studio-dev-a.2026-11-03.private-key.pem",
        )
        self.assertEqual(chosen, "rlgym-studio-dev-a.2026-11-03.private-key.pem")

    def test_same_date_is_broken_by_name(self) -> None:
        chosen = self.choose(
            "rlgym-studio-dev-a.2026-11-03.private-key.pem",
            "rlgym-studio-dev-a.2026-11-03.b.private-key.pem",
        )
        self.assertEqual(chosen, "rlgym-studio-dev-a.2026-11-03.private-key.pem")

    def test_modification_time_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            old = folder / "rlgym-studio-dev-a.2026-11-03.private-key.pem"
            new = folder / "rlgym-studio-dev-a.2026-12-01.private-key.pem"
            new.write_text("x")
            old.write_text("x")
            os.utime(new, (0, 0))  # the newer key has the older mtime
            self.assertEqual(as_app.key_path("rlgym-studio-dev-a", folder), new)

    def test_other_apps_keys_and_folders_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "rlgym-studio-dev-b.2030-01-01.private-key.pem").write_text("x")
            (folder / "rlgym-studio-dev-a.2031-01-01.private-key.pem").mkdir()
            with self.assertRaises(as_app.AsAppError) as caught:
                as_app.key_path("rlgym-studio-dev-a", folder)
            self.assertIn("no private key rlgym-studio-dev-a.*.pem", str(caught.exception))


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.github.com/x", code, "error", Message(), io.BytesIO(body))


class TokenExchangeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "rlgym-studio-dev-a.2026-11-03.private-key.pem"
        self.key.write_text(FAKE_KEY)
        patches = [
            mock.patch.dict(os.environ, {"STUDIO_AGENT_KEYS": self.tmp.name}),
            mock.patch.object(as_app, "sign_jwt", return_value="FAKE.JWT.VALUE"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def exchange_fails(self, error: Exception) -> str:
        def opener(request: object, timeout: float) -> FakeResponse:
            raise error

        with self.assertRaises(as_app.AsAppError) as caught:
            as_app.installation_token(APP, opener=opener)
        message = str(caught.exception)
        for secret in (FAKE_TOKEN, "FAKE.JWT.VALUE", "FAKE-KEY-MATERIAL", "PRIVATE KEY"):
            self.assertNotIn(secret, message)
        return message

    def test_success_returns_the_token(self) -> None:
        seen: list[object] = []

        def opener(request: object, timeout: float) -> FakeResponse:
            seen.append(request)
            return FakeResponse(json.dumps({"token": FAKE_TOKEN}).encode())

        self.assertEqual(as_app.installation_token(APP, opener=opener), FAKE_TOKEN)
        self.assertTrue(seen[0].full_url.endswith("/app/installations/2/access_tokens"))  # type: ignore[attr-defined]

    def test_http_401_names_the_likely_causes(self) -> None:
        message = self.exchange_fails(http_error(401, b'{"message": "A JSON web token could not be decoded"}'))
        self.assertIn("HTTP 401: A JSON web token could not be decoded", message)
        self.assertIn("wrong or revoked key", message)
        self.assertIn("rlgym-studio-dev-a", message)

    def test_http_404_points_at_the_installation(self) -> None:
        message = self.exchange_fails(http_error(404, b'{"message": "Not Found"}'))
        self.assertIn("HTTP 404: Not Found", message)
        self.assertIn("not installed", message)

    def test_http_error_with_unreadable_body(self) -> None:
        self.assertIn("HTTP 500", self.exchange_fails(http_error(500, b"<html>oops")))

    def test_network_error(self) -> None:
        message = self.exchange_fails(urllib.error.URLError("getaddrinfo failed"))
        self.assertIn("could not reach GitHub", message)
        self.assertIn("getaddrinfo failed", message)

    def test_answer_without_a_token(self) -> None:
        def opener(request: object, timeout: float) -> FakeResponse:
            return FakeResponse(b'{"expires_at": "soon"}')

        with self.assertRaises(as_app.AsAppError) as caught:
            as_app.installation_token(APP, opener=opener)
        self.assertIn("without a token", str(caught.exception))

    def test_main_prints_one_line_and_never_the_secret(self) -> None:
        error = http_error(401, b'{"message": "Bad credentials"}')
        stderr = io.StringIO()
        with (
            mock.patch.object(as_app, "installation_token", side_effect=as_app.exchange_error(APP, error)),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as caught,
        ):
            as_app.main(["dev-a", "--", "git", "status"])
        self.assertTrue(str(caught.exception.code).startswith("as_app: GitHub refused the token"))
        self.assertNotIn(FAKE_TOKEN, str(caught.exception.code))


class SignTest(unittest.TestCase):
    def test_bad_key_error_shows_no_key_material(self) -> None:
        fake_jwt = ModuleType("jwt")

        def encode(claims: object, key: str, algorithm: str) -> str:
            raise ValueError(f"Could not deserialize key data: {key}")

        fake_jwt.encode = encode  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "rlgym-studio-dev-a.2026-11-03.private-key.pem"
            key.write_text(FAKE_KEY)
            with mock.patch.dict("sys.modules", {"jwt": fake_jwt}), self.assertRaises(as_app.AsAppError) as caught:
                as_app.sign_jwt({}, key)
        message = str(caught.exception)
        self.assertIn(key.name, message)
        self.assertIn("ValueError", message)
        self.assertNotIn("FAKE-KEY-MATERIAL", message)
        self.assertIsNone(caught.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
