# Retrieval metrics

Each enrolled repository has an isolated hybrid index: SQLite FTS5/BM25, local code embeddings, and tree-sitter graph edges. Reciprocal Rank Fusion combines sparse and dense ranks. The index is not the source of truth. It rebuilds from git and human-readable memory records.

## What to measure

- Recall@k and MRR on fixture queries (`engine/tests/retrieval/`)
- Isolation: a hit from repository A must not appear in repository B
- Secret suppression: tokens and PEM material must not enter chunks
- Delete freshness: removed files must drop out of the index
- Fusion: sparse-only remains available when dense retrieval is degraded

## What not to copy

prior recall tests encoded product-specific booking/accessibility score boosts. Kronos does not ship query-specific constants. Golden retrieval uses fixture lessons without those hacks.

## Operations

Index health appears on the operator dashboard. Corrupt caches fail closed. Metrics stay in engine state and logs. Do not commit metrics YAML into the enrolled product repository.
