---
name: postgresql
description: Best practices and guidelines for working with PostgreSQL. Covers schema design, indexing strategies, query optimization, migrations, embedded PostgreSQL on Windows, and lock resolution.
---

# PostgreSQL Best Practices

Guidelines and best practices for working with Postgres, covering schema design, indexing, query optimization, common pitfalls, and embedded execution.

## Supported Versions

This skill covers PostgreSQL 14 through 18. Version-specific features are tagged (e.g., `[PG15+]`, `[PG18+]`); environment-dependent examples identify required privileges, extensions, or multi-node setup.

PostgreSQL provides 5 years of support per major version. Always run the latest minor release.

| Version | Initial Release    | End of Life        |
| ------- | ------------------ | ------------------ |
| 18      | September 2025     | November 2030      |
| 17      | September 2024     | November 2029      |
| 16      | September 2023     | November 2028      |
| 15      | October 2022       | November 2027      |
| 14      | September 2021     | November 2026      |

Source: [postgresql.org/support/versioning](https://www.postgresql.org/support/versioning/)

## References

| Area                    | Resource                                | When to Use                                                        |
| ----------------------- | --------------------------------------- | ------------------------------------------------------------------ |
| Schema Design           | `references/schema-design.md`           | Designing tables, choosing data types, normalizing, partitioning   |
| Indexing                | `references/indexing.md`                | Choosing index types, composite indexes, partial/covering indexes  |
| Query Optimization      | `references/query-optimization.md`      | Reading EXPLAIN ANALYZE, fixing bottlenecks, planner tuning        |
| Query Patterns          | `references/query-patterns.md`          | CTEs, window functions, lateral joins, UPSERT, JSONB, anti-patterns|
| Performance Diagnostics | `references/performance-diagnostics.md` | pg_stat views, lock analysis, VACUUM, connection management        |
| Logical Replication     | `references/logical-replication.md`     | Pub/sub replication, live migrations, CDC                          |
| Hot Standby             | `references/hot-standby.md`             | Streaming replication, read replicas, failover                     |
| Transaction Isolation   | `references/transaction-isolation.md`   | Isolation levels, lost updates, serialization failures, retry logic |
| Backup & Restore        | `references/backup-restore.md`          | pg_dump/pg_restore, pg_basebackup, PITR, recovery                 |
| Security & Roles        | `references/security-roles.md`          | Privileges, RLS, pg_hba.conf, authentication, SSL                 |
| Bulk Data Loading       | `references/bulk-loading.md`            | COPY patterns, ETL staging, optimizing large loads, batch ops      |
| Connection Pooling      | `references/connection-pooling.md`      | PgBouncer config, pool modes, prepared statements, sizing          |
| Major Version Upgrades  | `references/major-version-upgrades.md`  | pg_upgrade, logical replication migration, pre/post checklists     |

---

## Embedded PostgreSQL on Windows Guidelines

When running embedded PostgreSQL inside Python automated environments, local workbenches (Pixeltable), or test scripts on Windows, lock file conflicts (such as `postmaster.pid` blockages) and port collisions are common points of failure. Windows handles file locking much more rigidly than Unix-like systems.

### 1. Dynamic Port Allocation
Never hardcode the default PostgreSQL port. Parallel scripts will collide and trigger network socket lock errors.
- Bind dynamically or discover an open socket prior to launching.
- Pass the assigned port explicitly to your embedded server instance configuration.

### 2. Isolated Data Directories
Shared data directories cause severe PID conflicts and state corruption when multiple scripts execute simultaneously.
- Use distinct data directories for automated test runs versus development databases.
- Enforce absolute separation between concurrent runner processes.

### 3. Strict Context Management & Cleanup
Windows locks files aggressively. If a script crashes or an unhandled exception is thrown, the `postgres.exe` process may remain orphaned, holding a lock on the data directory.
- Wrap server lifecycles inside native Python context managers (`with` statements).
- Implement exhaustive `try...finally` or signal handler blocks to guarantee shutdown.
- Explicitly call the stop command of your embedded database driver before exiting.

### 4. Aggressive Orphaned Process Purging
In high-throughput automated grading or agent environments:
- Execute a pre-flight sweep to terminate dangling `postgres.exe` engines before starting new tests.
- Clean up lingering `postmaster.pid` files if they survive an abrupt process termination (`Ctrl+C`).
