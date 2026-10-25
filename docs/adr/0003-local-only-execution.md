# ADR-0003: Training runs locally only

- Status: Accepted (2026-10-25), decided by the owner

## Decision
Training always runs as child processes of the local backend on the user's machine. Remote workers and cluster
scheduling are explicit non-goals.

## Consequences
The backend runner can rely on local process control, local GPUs and direct file access. The runner still sits behind an
interface for testability (e.g. a fake runner in tests), but nothing is built for remote execution.
