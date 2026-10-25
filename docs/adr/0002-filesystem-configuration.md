# ADR-0002: Configuration persisted on the file system

- Status: Accepted (2026-10-25)

## Context
The owner's previous iteration stored configuration on disk. rlgym-learn itself uses file-based configuration.

## Decision
Projects, agent/training configurations and run metadata are stored as human-readable files (one folder per project
and run) under a user-chosen workspace directory. Every file carries a `schemaVersion`, and the backend applies
forward migrations when it loads a file. Only the backend reads or writes these files.

## Consequences
Configs can be diffed, committed to git by users, and shared. Querying across many runs needs an index, which can be
rebuilt from disk at any time and is never the source of truth. A database requires a superseding ADR.
