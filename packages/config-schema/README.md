# packages/config-schema — studio file schemas

**Owner track:** A (`track-a`, DEV-A). **Language:** Python (uv workspace member `studio-config-schema`).

Versioned models for the files the studio persists (project and run envelopes with `schemaVersion`, embedding the
upstream rlgym-learn config verbatim), their published JSON Schema, and forward migrations (ADR-0002).

## Boundaries (ADR-0001)
- Packages never import from `apps/*`. Apps never import from each other: they talk only through the HTTP/WS
  contract (`packages/contract`).
- This folder must stay extractable into its own repository without code changes (own manifest, tests and README).
- Does not import rlgym-learn: the upstream config is embedded as opaque JSON; its schema comes from introspection
  in the user's interpreter (see `packages/rlgym-adapter`).

## File types

| Kind | File | Model | Current `schemaVersion` | JSON Schema |
|---|---|---|---|---|
| `project` | `<workspace>/<id>/project.json` | `ProjectFile` | 1 | [`schemas/project.v1.schema.json`](schemas/project.v1.schema.json) |

Every file is an **envelope** (`Envelope`): `kind` + `schemaVersion`, then the file type's fields. `schemaVersion` is
a per-file-type integer counting up from 1 during 0.x; at 1.0.0 the versions in use are frozen as the public baseline.

## Usage

```python
from pathlib import Path
from studio_config_schema import ProjectFile, SchemaFileError, load, save

try:
    project = load(Path("my-project/project.json"), ProjectFile)
except SchemaFileError as error:
    print(error.reason, error.path, error.pointer, error.message)  # e.g. invalid_content … /name …
else:
    save(Path("my-project/project.json"), project.model_copy(update={"name": "Renamed"}))
```

## Older files: migrations (TC-33)

Each file type has a sealed chain of `vN -> vN+1` steps (`Migrations`, next to its model). Loading a file
older than the current version runs every step on the raw JSON, then validates the result with the current model.

| Function | Writes? | Use |
|---|---|---|
| `load(path, Model)` / `loads(data, Model)` | never | read-only callers: migrate in memory |
| `read(path, Model)` | never | as `load`, plus `migrated_from` (the old version, or `None`) |
| `upgrade(path, Model)` | only if migrated | copies the original to `.backup/<file name>.v<old>.<YYYYMMDDTHHMMSSZ>.json` (never overwrites one: `-2`, `-3`...), then rewrites the file atomically |

A current file is never rewritten (same bytes, same mtime). A too-new file is never migrated or written
(`too_new`). A step that raises leaves the file untouched (`migration_failed`, naming the step). A chain with a gap,
a duplicate step or a step past the current version fails at import.

### Adding a version of a file type (e.g. project v1 -> v2)

1. **Corpus first:** make sure `tests/fixtures/<kind>/v1/` has samples of the old format. Never edit an existing
   sample: the corpus is append-only, and the CI hook `corpus-immutable` fails on any change, deletion or rename.
2. **Bump:** in the model, `SCHEMA_VERSION = 2`, `schema_version: Literal[2]`, `Migrations("<kind>", current=2)`.
3. **Migration:** `@<KIND>_MIGRATIONS.step(1)` taking and returning the raw dict (never the model), placed before
   `.seal()`. It must not depend on the current model, which will change again.
4. **Corpus sample for v2:** add `tests/fixtures/<kind>/v2/*.json`. `test_every_corpus_sample_loads` loads every
   sample of every version with the current code, and `test_corpus_layout` wants one folder per readable version.
5. **Schema:** run `generate-schemas`. It writes `schemas/<kind>.v2.schema.json`; keep the committed v1 file.
6. **Tell QA** to regenerate `tests/fixtures/workspaces` (TC-42 agreement) and activate X2-2b in the test plan.

## Rules a file follows

- **Unknown top-level keys are kept.** Load then save gives the same data, so a newer studio's fields and keys a
  user added by hand are not lost. They are not validated.
- **Optional fields absent from a file stay absent** when it is saved again; an unchanged file saves to the same bytes.
- **Canonical bytes on save:** UTF-8 without BOM and without `\u` escapes, LF, 2-space indent, the envelope's
  top-level keys sorted, one trailing newline, timestamps as `YYYY-MM-DDTHH:MM:SSZ`. The content of `upstream` (and
  of unknown keys) keeps its key order and JSON values; number *spelling* is not preserved (`1e5` is written back
  as `100000.0`, `1.50` as `1.5`). Numbers out of float range (`1e400`), `NaN` and `Infinity` are refused on load.
- **Lenient on load:** a UTF-8 BOM, CRLF, fractional seconds and `+00:00`/other offsets are accepted and normalised on
  the next save. A timestamp without an offset is refused.
- **Strict types:** `"1"` is not an integer, `"yes"` is not a boolean.

## Errors

Every content problem raises **`SchemaFileError`** with:

| Attribute | Meaning |
|---|---|
| `path` | the file (`None` when parsed from memory) |
| `reason` | `invalid_json` (empty, syntax, NaN, not UTF-8), `invalid_content` (not an object, missing field, wrong type or value), `too_new` (`schemaVersion` newer than supported), `migration_failed` (an older file's migration step raised; the message names the step) |
| `pointer`, `message` | RFC 6901 JSON pointer (`""` = whole document, e.g. `/archived`) and a human message for the first issue |
| `issues` | every issue found, each with `pointer` and `message` |

File-system errors (missing file, permission denied) are not content problems and propagate as `OSError`.

## JSON Schema

`schemas/<kind>.v<N>.schema.json` is generated from the models (JSON Schema 2020-12, with `$id`). After changing a
model, regenerate and commit:

```bash
uv run --package studio-config-schema generate-schemas
```

`tests/test_schemas.py` fails while a committed schema differs from the generated one. A published version's file
never changes once released: a format change is a new `schemaVersion` with its own file and a migration (TC-33).

## Tests and fixtures

```bash
uv run --package studio-config-schema pytest packages/config-schema
```

- `tests/fixtures/<kind>/v<N>/`: samples of each released version, append-only (CI hook `corpus-immutable`).
  `sample/` is a test-only kind (`tests/sample_kind.py`, v0 -> v1) that proves the migration mechanism; the shipped
  package never registers it.
- QA's whole-workspace fixtures in the repository's `tests/fixtures/` are also read as data when present; those tests
  are skipped once the package lives in its own repository.
