# DECISIONS.md

## Phase 1 implementation decisions

1. **Preserve source CSV rows as JSONB.** The task kit contains several datasets with different schemas. A staging table preserves every supplied field without prematurely locking in a final normalized schema. Typed domain tables can be introduced after validation.
2. **Use source identifiers as idempotency keys.** Re-importing replaces each dataset's staged rows and uses dataset + record key uniqueness to avoid duplicates.
3. **Keep policy content separate from code.** Policy v5.0 is seeded into `policy_versions.policy_data` as structured JSON. The decision evaluator will consume this data in a later phase.
4. **No inferred item matches in Phase 1.** Item matching and confidence thresholds belong to the decision/intake implementation and will be explicitly tested.
5. **Use local PostgreSQL by default.** Docker Compose is included as an optional database alternative, not a requirement if PostgreSQL is already installed.
