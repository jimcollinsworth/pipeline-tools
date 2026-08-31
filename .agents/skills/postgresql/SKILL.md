\---

name: postgres-best-practices

description: Best practices and guidelines for working with Postgres. Covers schema design, indexing strategies, query optimization, migrations, and common pitfalls. Use when writing SQL, designing database schemas, optimizing queries, or setting up a Postgres database.

\---



\# Postgres Best Practices



Guidelines and best practices for working with Postgres, covering schema design, indexing, query optimization, and common pitfalls.



\## Supported Versions



This skill covers PostgreSQL 14 through 18. Version-specific features are tagged (e.g., `\[PG15+]`, `\[PG18+]`); environment-dependent examples identify required privileges, extensions, or multi-node setup.



PostgreSQL provides 5 years of support per major version. Always run the latest minor release.



| Version | Initial Release    | End of Life        |

| ------- | ------------------ | ------------------ |

| 18      | September 2025     | November 2030      |

| 17      | September 2024     | November 2029      |

| 16      | September 2023     | November 2028      |

| 15      | October 2022       | November 2027      |

| 14      | September 2021     | November 2026      |



Source: \[postgresql.org/support/versioning](https://www.postgresql.org/support/versioning/)



\## References



| Area                    | Resource                                | When to Use                                                        |

| ----------------------- | --------------------------------------- | ------------------------------------------------------------------ |

| Schema Design           | `references/schema-design.md`           | Designing tables, choosing data types, normalizing, partitioning   |

| Indexing                | `references/indexing.md`                | Choosing index types, composite indexes, partial/covering indexes  |

| Query Optimization      | `references/query-optimization.md`      | Reading EXPLAIN ANALYZE, fixing bottlenecks, planner tuning        |

| Query Patterns          | `references/query-patterns.md`          | CTEs, window functions, lateral joins, UPSERT, JSONB, anti-patterns|

| Performance Diagnostics | `references/performance-diagnostics.md` | pg\_stat views, lock analysis, VACUUM, connection management        |

| Logical Replication     | `references/logical-replication.md`     | Pub/sub replication, live migrations, CDC                          |

| Hot Standby             | `references/hot-standby.md`             | Streaming replication, read replicas, failover                     |

| Transaction Isolation   | `references/transaction-isolation.md`   | Isolation levels, lost updates, serialization failures, retry logic |

| Backup \& Restore        | `references/backup-restore.md`          | pg\_dump/pg\_restore, pg\_basebackup, PITR, recovery                 |

| Security \& Roles        | `references/security-roles.md`          | Privileges, RLS, pg\_hba.conf, authentication, SSL                 |

| Bulk Data Loading       | `references/bulk-loading.md`            | COPY patterns, ETL staging, optimizing large loads, batch ops      |

| Connection Pooling      | `references/connection-pooling.md`      | PgBouncer config, pool modes, prepared statements, sizing          |

| Major Version Upgrades  | `references/major-version-upgrades.md`  | pg\_upgrade, logical replication migration, pre/post checklists     |







When running embedded PostgreSQL inside Python automated environments or skills test scripts on Windows, lock file conflicts (like  blockages) and port collisions are the most common points of failure. Windows handles file locking much more rigidly than Unix-like systems, which means a single crashed test script can completely stall an entire evaluation pipeline. \[1, 2, 3]  

Follow these best practices to ensure seamless, isolated, and conflict-free embedded Postgres execution on Windows. 

1\. Dynamic Port Allocation 

Never hardcode the default PostgreSQL port (). Parallel test scripts will immediately collide and trigger network socket lock errors. 



• Find a free port dynamically right before initiating the server. 

• Bind temporarily to port  or use a utility function to discover an open socket. 

• Pass the assigned port explicitly to your embedded server instance configuration. 



2\. Isolated Data Directories 

Shared data directories cause severe  conflicts and state corruption when multiple scripts execute simultaneously. 



• Generate unique temporary directories for every single test execution. 

• Utilize Python's  to automatically handle path uniqueness. 

• Enforce absolute separation between concurrent agent scripts. 



3\. Strict Context Management \& Cleanup 

Windows locks files aggressively. If a test script crashes or an exception is thrown, the  process may remain orphaned, holding a lock on the data directory. 



• Wrap server lifecycles inside native Python context managers ( statements). 

• Implement exhaustive  blocks to guarantee the shutdown sequence fires. 

• Explicitly call the stop command of your embedded library before exiting the script. \[4]  



4\. Aggressive Orphaned Process Purging 

In high-throughput automated grading or agent environments, unexpected script terminations are inevitable. 



• Execute a pre-flight sweep to kill dangling  engines before starting new tests. 

• Clean up lingering  files manually if they survive a crash. 

• Automate this cleanup within your main test orchestrator or setup scripts. 



5\. Leverage Production-Ready Libraries 

Avoid rolling a custom solution using raw  calls to  and . 



• Use pgembed: It provides pip-installable binaries for Windows and handles , automatic port binding, and automated cleanup natively. 

• Use : If your testing infrastructure relies on pytest, this plugin manages the lifecycle of ephemeral databases reliably across platforms. \[1]  



AI responses may include mistakes.



\[1] https://github.com/Ladybug-Memory/pgembed

\[2] https://medium.com/@aman.deep291098/avoiding-file-conflicts-in-multithreaded-python-programs-34f2888f4521

\[3] https://stackoverflow.com/questions/38642623/how-to-test-file-locking-in-python

\[4] https://www.youtube.com/shorts/Y1qF8ABzqyU





