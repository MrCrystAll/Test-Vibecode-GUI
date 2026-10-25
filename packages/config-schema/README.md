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
