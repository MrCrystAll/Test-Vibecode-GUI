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
Roles and IDs live in `apps.json` next to this file.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

import jwt

HERE = pathlib.Path(__file__).resolve().parent
API = "https://api.github.com"


def key_path(slug: str) -> pathlib.Path:
    folder = pathlib.Path(os.environ.get("STUDIO_AGENT_KEYS", pathlib.Path.home() / ".studio-agents"))
    keys = sorted(folder.glob(f"{slug}.*.pem"))
    if not keys:
        sys.exit(f"as_app: no private key {slug}.*.pem in {folder}")
    return keys[-1]  # newest by date in the file name, so a rotated key wins


def installation_token(app: dict) -> str:
    now = int(time.time())
    claims = {"iat": now - 60, "exp": now + 540, "iss": str(app["app_id"])}
    app_jwt = jwt.encode(claims, key_path(app["slug"]).read_text(), algorithm="RS256")
    request = urllib.request.Request(
        f"{API}/app/installations/{app['installation_id']}/access_tokens",
        method="POST",
        headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["token"]


def main(argv: list[str]) -> int:
    apps = json.loads((HERE / "apps.json").read_text())
    if len(argv) < 3 or argv[1] != "--" or argv[0] not in apps:
        sys.exit(f"usage: as_app.py <{'|'.join(apps)}> -- <command> [args...]")
    app = apps[argv[0]]
    token = installation_token(app)
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
