# M4 Batch C privacy-readiness

- Added idempotent Batch C task records and promotion gates; production memory remains blocked.
- Added a provider decision packet limited to verifiable paid no-training or self-hosted options; no provider, spend, credential, or live call selected.
- Added a deterministic synthetic English/Urdu/Roman Urdu memory-extraction evaluation fixture and offline runner.
- Added PostgreSQL `customers.memory_version` migration and a fail-closed stale queued-work guard; extraction flag defaults false.
- Preserved FastAPI sessions, PostgreSQL sole app DB, explicit customer controls, no-silent-relaxation, and Batch A/B baselines.
