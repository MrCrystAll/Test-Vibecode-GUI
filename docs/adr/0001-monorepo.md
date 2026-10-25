# ADR-0001: Split-ready monorepo

- Status: Accepted (2026-10-25)

## Context
The product is meant to live for years and may later be split across a GitHub organization. Early on, most changes cut
across the UI, backend and API contract.

## Decision
One repository with `apps/` (desktop, ui, backend) and `packages/` (contract, config schema, rlgym adapter, ...).
Apps communicate only through the HTTP/WS contract. Packages never depend on apps. Each package has its own manifest,
tests and README, so it can be extracted into its own repository without code changes.

## Consequences
Atomic cross-cutting PRs while the API is still young. Boundaries are enforced by lint rules / import checks, not by
repository walls. Revisit before 1.0.0 if a package needs an independent release cadence.
