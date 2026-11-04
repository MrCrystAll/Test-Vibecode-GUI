# SPDX-License-Identifier: Apache-2.0
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyjwt[crypto]>=2.8"]
# ///
"""Run a `gh` or `git` command as an agent's own GitHub App (TC-47, workflow.md "GitHub identities").

    uv run --script tools/agent/as_app.py dev-a -- gh pr create --base dev --fill
    uv run --script tools/agent/as_app.py dev-b -- gh pr review 42 --approve --body "[DEV-B] APPROVED at <sha>"
    uv run --script tools/agent/as_app.py dev-a -- git push -u origin feat/TC-n-slug
    uv run --script tools/agent/as_app.py dev-a -- git commit -m "feat(backend): ... (TC-n)"

How it works: the app's private key (outside the repo, in `%USERPROFILE%/.studio-agents/<slug>.*.pem`, or the folder
in `STUDIO_AGENT_KEYS`) signs a 9-minute JWT, which GitHub exchanges for a 1-hour installation token scoped to this
repository. The command then runs with:
- `GH_TOKEN` set, so `gh` acts as `<slug>[bot]`;
- an HTTP auth header for github.com passed to git through `GIT_CONFIG_*` variables, so pushes use the app;
- author and committer set to the bot, so commits are attributed to it.

The token lives only in the child process's environment: it is never printed, logged or written to disk.
Roles and IDs live in `apps.json` next to this file. With several keys for one app, the newest date in the file
name wins (`key_order`). Failures print one `as_app: ...` line with GitHub's status and message, never a credential.
Self-tests: tools/ci/tests/test_as_app.py (no network, no real keys).
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
API = "https://api.github.com"


# GitHub names downloaded keys `<slug>.<YYYY-MM-DD>.private-key.pem`.
DATED_KEY = re.compile(r"\.(\d{4}-\d{2}-\d{2})\.")


class AsAppError(Exception):
    """A failure reported to the user as one line. Never carries key or token material."""


def key_order(path: pathlib.Path) -> tuple[int, str, str]:
    """Sort key for candidate key files: the newest wins (TC-49).

    1. A file with a date in its name (`<slug>.2026-11-03.private-key.pem`) beats one without.
    2. Among dated files, the latest date wins; among undated ones, nothing else applies.
    3. Ties are broken by the full file name, so the choice never depends on the file system's listing order.
    Modification times are ignored: copying a folder changes them.
    """
    match = DATED_KEY.search(path.name)
    return (1, match.group(1), path.name) if match else (0, "", path.name)


def key_path(slug: str, folder: pathlib.Path | None = None) -> pathlib.Path:
    if folder is None:
        folder = pathlib.Path(os.environ.get("STUDIO_AGENT_KEYS", pathlib.Path.home() / ".studio-agents"))
    keys = [p for p in folder.glob(f"{slug}.*.pem") if p.is_file()]
    if not keys:
        raise AsAppError(f"no private key {slug}.*.pem in {folder}")
    return max(keys, key=key_order)


def sign_jwt(claims: dict, key_file: pathlib.Path) -> str:
    import jwt  # third-party; imported here so the self-tests run on the standard library only

    try:
        return jwt.encode(claims, key_file.read_text(), algorithm="RS256")
    except Exception as exc:  # noqa: BLE001 - the library's message may quote the key, so show only the type
        message = f"could not sign a JWT with {key_file.name} ({type(exc).__name__}); is it a valid RSA key?"
        raise AsAppError(message) from None


def exchange_error(app: dict, exc: Exception) -> AsAppError:
    """A readable message for a failed token exchange: GitHub's status and message, never a credential."""
    where = f"installation {app['installation_id']} of app {app['slug']} (id {app['app_id']})"
    if isinstance(exc, urllib.error.HTTPError):
        detail = ""
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            if isinstance(body, dict) and isinstance(body.get("message"), str):
                detail = f": {body['message']}"
        except (ValueError, OSError):
            pass
        hint = {
            401: " (wrong app id, wrong or revoked key, or a clock more than a minute off)",
            404: " (wrong installation id, or the app is not installed on the repository)",
        }.get(exc.code, "")
        return AsAppError(f"GitHub refused the token for {where}: HTTP {exc.code}{detail}{hint}")
    if isinstance(exc, urllib.error.URLError):
        return AsAppError(f"could not reach GitHub for {where}: {exc.reason}")
    return AsAppError(f"token exchange for {where} failed: {type(exc).__name__}")


def installation_token(app: dict, opener=urllib.request.urlopen) -> str:
    now = int(time.time())
    claims = {"iat": now - 60, "exp": now + 540, "iss": str(app["app_id"])}
    app_jwt = sign_jwt(claims, key_path(app["slug"]))
    request = urllib.request.Request(
        f"{API}/app/installations/{app['installation_id']}/access_tokens",
        method="POST",
        headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
    )
    try:
        with opener(request, timeout=30) as response:
            token = json.load(response).get("token")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise exchange_error(app, exc) from None
    if not isinstance(token, str) or not token:
        raise AsAppError(f"GitHub answered without a token for installation {app['installation_id']}")
    return token


def main(argv: list[str]) -> int:
    apps = json.loads((HERE / "apps.json").read_text())
    if len(argv) < 3 or argv[1] != "--" or argv[0] not in apps:
        sys.exit(f"usage: as_app.py <{'|'.join(apps)}> -- <command> [args...]")
    app = apps[argv[0]]
    try:
        token = installation_token(app)
    except AsAppError as exc:
        sys.exit(f"as_app: {exc}")
    bot = f"{app['slug']}[bot]"
    email = f"{app['bot_user_id']}+{bot}@users.noreply.github.com"
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()

    env = dict(os.environ)
    env.update(
        GH_TOKEN=token,
        GIT_AUTHOR_NAME=bot,
        GIT_AUTHOR_EMAIL=email,
        GIT_COMMITTER_NAME=bot,
        GIT_COMMITTER_EMAIL=email,
        # Replace any stored credential for github.com with the app's token, for this one command only.
        GIT_CONFIG_COUNT="2",
        GIT_CONFIG_KEY_0="credential.https://github.com.helper",
        GIT_CONFIG_VALUE_0="",
        GIT_CONFIG_KEY_1="http.https://github.com/.extraheader",
        GIT_CONFIG_VALUE_1=f"AUTHORIZATION: basic {basic}",
    )
    return subprocess.run(argv[2:], env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
