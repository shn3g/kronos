# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import platform
import time
from pathlib import Path

from tests.retrieval.support import golden_fixture, indexing_policy, kronos_paths

from kronos_engine.indexing.service import IndexingService

GOLDEN = Path(__file__).parent / "golden" / "queries.json"


def test_hybrid_matches_or_beats_sparse_on_golden_queries(tmp_path: Path) -> None:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    queries = payload["queries"]
    k = int(payload["k"])
    paths = kronos_paths(tmp_path)
    root = golden_fixture(tmp_path / "golden")
    service = IndexingService(paths)
    started = time.perf_counter()
    status = service.rebuild("repo_golden", root, indexing_policy())
    index_seconds = time.perf_counter() - started
    assert status.chunk_count > 0
    assert status.disk_bytes > 0

    cold_started = time.perf_counter()
    service.search("repo_golden", queries[0]["query"], mode="hybrid")
    cold_ms = (time.perf_counter() - cold_started) * 1000
    warm_started = time.perf_counter()
    service.search("repo_golden", queries[0]["query"], mode="hybrid")
    warm_ms = (time.perf_counter() - warm_started) * 1000

    sparse_recall, sparse_mrr = _score(service, queries, k, "sparse")
    hybrid_recall, hybrid_mrr = _score(service, queries, k, "hybrid")
    metrics = {
        "hardware": {
            "system": platform.system(),
            "machine": platform.machine(),
            "processor": platform.processor() or "unknown",
            "python": platform.python_version(),
        },
        "index_seconds": index_seconds,
        "disk_bytes": status.disk_bytes,
        "cold_latency_ms": cold_ms,
        "warm_latency_ms": warm_ms,
        "sparse": {"recall_at_k": sparse_recall, "mrr": sparse_mrr},
        "hybrid": {"recall_at_k": hybrid_recall, "mrr": hybrid_mrr},
    }
    assert metrics["hybrid"]["recall_at_k"] >= metrics["sparse"]["recall_at_k"]
    assert metrics["hybrid"]["mrr"] >= metrics["sparse"]["mrr"]
    assert hybrid_recall > 0
    graph_query = next(item for item in queries if item["id"] == "graph-tests-of-connect")
    hybrid_hits = service.search("repo_golden", graph_query["query"], mode="hybrid", limit=k)
    sparse_hits = service.search("repo_golden", graph_query["query"], mode="sparse", limit=k)
    hybrid_paths = [item.path.replace("\\", "/") for item in hybrid_hits.items]
    sparse_paths = [item.path.replace("\\", "/") for item in sparse_hits.items]
    assert "tests/test_db.py" in hybrid_paths
    assert "tests/test_db.py" not in sparse_paths
    for item in hybrid_hits.items:
        assert item.commit
        assert item.path
        assert item.start_line >= 1
        assert item.rank_sources
        assert item.trust


def _score(
    service: IndexingService, queries: list[dict[str, object]], k: int, mode: str
) -> tuple[float, float]:
    recalls: list[float] = []
    rr: list[float] = []
    for query in queries:
        pack = service.search("repo_golden", str(query["query"]), mode=mode, limit=k)
        paths = [item.path.replace("\\", "/") for item in pack.items]
        relevant = {str(path).replace("\\", "/") for path in query["relevant_paths"]}  # type: ignore[union-attr]
        hits = relevant.intersection(paths)
        recalls.append(len(hits) / len(relevant))
        rank = next((index + 1 for index, path in enumerate(paths) if path in relevant), 0)
        rr.append(0.0 if rank == 0 else 1.0 / rank)
    return sum(recalls) / len(recalls), sum(rr) / len(rr)
