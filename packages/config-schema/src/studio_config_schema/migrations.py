# SPDX-License-Identifier: Apache-2.0
"""Forward-only migrations between versions of one file type (TC-33).

A file type declares its chain next to its model, then seals it at the end of the module:

    MIGRATIONS = Migrations("project", current=2)

    @MIGRATIONS.step(1)          # v1 -> v2
    def _rename_title(data: dict[str, Any]) -> dict[str, Any]:
        data["name"] = data.pop("title")
        return data

    MIGRATIONS.seal()            # import fails here on a gap or a step past the current version

A step works on the **raw JSON object** (a dict), never on the current model: the model changes
with every version, a migration must not. Each step receives its own deep copy and returns the next
version's object; the chain sets `schemaVersion` itself. A duplicate step fails as soon as it is
declared.
"""

import copy
from collections.abc import Callable
from typing import Any

JsonObject = dict[str, Any]
Step = Callable[[JsonObject], JsonObject]


class MigrationChainError(Exception):
    """A file type's chain is malformed (gap, duplicate, step out of range): a programming error."""


class MigrationStepError(Exception):
    """A step raised. `from_version` names the step (`from_version -> from_version + 1`)."""

    def __init__(self, kind: str, from_version: int, cause: BaseException) -> None:
        self.kind = kind
        self.from_version = from_version
        self.cause = cause
        super().__init__(
            f"migration of {kind} v{from_version} -> v{from_version + 1} failed: "
            f"{type(cause).__name__}: {cause}"
        )


class Migrations:
    """The ordered `vN -> vN+1` steps of one file type, oldest readable version to current."""

    def __init__(self, kind: str, *, current: int) -> None:
        if current < 1:
            raise MigrationChainError(f"{kind}: current version must be >= 1, got {current}")
        self.kind = kind
        self.current = current
        self._steps: dict[int, Step] = {}
        self._sealed = False

    def step(self, from_version: int) -> Callable[[Step], Step]:
        """Declare the migration from `from_version` to `from_version + 1`."""

        def register(function: Step) -> Step:
            if self._sealed:
                raise MigrationChainError(f"{self.kind}: chain already sealed")
            if from_version in self._steps:
                raise MigrationChainError(
                    f"{self.kind}: duplicate step v{from_version} -> v{from_version + 1}"
                )
            self._steps[from_version] = function
            return function

        return register

    def seal(self) -> "Migrations":
        """Check the chain is contiguous and ends at `current`. Call it once, at import time."""
        if self._steps:
            versions = sorted(self._steps)
            if versions[-1] != self.current - 1:
                raise MigrationChainError(
                    f"{self.kind}: the last step must be v{self.current - 1} -> v{self.current}, "
                    f"found v{versions[-1]} -> v{versions[-1] + 1}"
                )
            missing = sorted(set(range(versions[0], self.current)) - set(versions))
            if missing:
                gaps = ", ".join(f"v{v} -> v{v + 1}" for v in missing)
                raise MigrationChainError(
                    f"{self.kind}: gap in the migration chain, missing {gaps}"
                )
        self._sealed = True
        return self

    @property
    def oldest(self) -> int:
        """The oldest `schemaVersion` this chain can read."""
        return min(self._steps, default=self.current)

    def migrate(self, data: JsonObject, from_version: int) -> JsonObject:
        """Apply every step from `from_version` to `current`. The input is never modified."""
        if not self._sealed:
            raise MigrationChainError(f"{self.kind}: chain used before seal()")
        if not self.oldest <= from_version <= self.current:
            raise MigrationChainError(
                f"{self.kind}: cannot migrate from v{from_version} "
                f"(readable: v{self.oldest} to v{self.current})"
            )
        current = copy.deepcopy(data)
        for version in range(from_version, self.current):
            try:
                result = self._steps[version](copy.deepcopy(current))
                if not isinstance(result, dict):
                    raise TypeError(f"the step returned {type(result).__name__}, not an object")
            except Exception as exc:  # reported with the step that failed
                raise MigrationStepError(self.kind, version, exc) from exc
            result["schemaVersion"] = version + 1
            current = result
        return current
