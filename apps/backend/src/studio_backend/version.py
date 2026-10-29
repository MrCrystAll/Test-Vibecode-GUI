# SPDX-License-Identifier: Apache-2.0
"""Version information exposed by `/api/version`."""

from importlib.metadata import version

DISTRIBUTION_NAME = "studio-backend"

# Version of the HTTP/WS contract, independent of the app version. Bumped by hand when the
# contract changes; frozen under semver from 1.0.0 (CLAUDE.md rule 2).
API_VERSION = "0.1.0"


def app_version() -> str:
    """Return the installed backend version from package metadata."""
    return version(DISTRIBUTION_NAME)
