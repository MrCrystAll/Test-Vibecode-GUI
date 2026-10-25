# SPDX-License-Identifier: Apache-2.0
"""CI hook (TC-18, ADR-0006 drift check): packages/contract/openapi.json must match the backend routes.

Run by tools/ci/run.py (`hooks` step) from the repository root. TC-22 adds the second half of the check
(regenerating the TypeScript client and diffing it).
"""

import subprocess
import sys

sys.exit(
    subprocess.run(  # noqa: S603 - fixed command
        ["uv", "run", "--locked", "--package", "studio-backend", "export-openapi", "--check"],  # noqa: S607
        check=False,
    ).returncode
)
