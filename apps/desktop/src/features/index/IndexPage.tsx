// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionRepositoriesClient,
  type EnrolledRepository,
} from "../workspaces/client";
import {
  createProductionIndexClient,
  type IndexClient,
  type IndexHit,
  type IndexStatus,
} from "./client";

export type { IndexClient } from "./client";

export interface IndexPageClients extends IndexClient {
  listRepositories(): Promise<EnrolledRepository[]>;
}

interface IndexPageProps {
  engineClient: EngineClient;
  indexClient?: IndexPageClients;
}

const productionIndex = createProductionIndexClient();
const productionRepos = createProductionRepositoriesClient();
const productionPageClient: IndexPageClients = {
  ...productionIndex,
  listRepositories: () => productionRepos.list(),
};

export function IndexPage({ engineClient, indexClient }: IndexPageProps) {
  const client = indexClient ?? productionPageClient;
  const [ready, setReady] = useState(false);
  const [repositories, setRepositories] = useState<EnrolledRepository[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<IndexHit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const selectedRef = useRef(selectedId);
  const requestGen = useRef(0);
  selectedRef.current = selectedId;

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engineClient.getState().then((state) => {
        if (!cancelled) {
          setReady(state.status === "ready");
        }
      });
    };
    apply();
    const interval = window.setInterval(apply, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [engineClient]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    let cancelled = false;
    void client.listRepositories().then((items) => {
      if (cancelled) {
        return;
      }
      setRepositories(items);
      setSelectedId((current) => current || items[0]?.id || "");
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  useEffect(() => {
    if (!ready || !selectedId) {
      return;
    }
    const gen = requestGen.current;
    let cancelled = false;
    const refresh = () => {
      const repoId = selectedId;
      void client.status(repoId).then((next) => {
        if (!cancelled && requestGen.current === gen && selectedRef.current === repoId) {
          setStatus(next);
        }
      });
    };
    refresh();
    const interval = window.setInterval(refresh, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [client, ready, selectedId]);

  if (!ready) {
    return (
      <section className="index-page">
        <p className="page-kicker">Index</p>
        <h1 className="page-title">Index</h1>
        <p className="page-body">
          Connect a compatible engine to inspect repository indexes. Retrieval stays closed until
          the local engine is ready.
        </p>
      </section>
    );
  }

  function selectRepository(id: string) {
    requestGen.current += 1;
    setSelectedId(id);
    setHits([]);
    setStatus(null);
    setError(null);
  }

  async function onRebuild() {
    if (!selectedId) {
      return;
    }
    const repoId = selectedId;
    const gen = requestGen.current;
    setError(null);
    try {
      const next = await client.rebuild(repoId);
      if (requestGen.current !== gen || selectedRef.current !== repoId) {
        return;
      }
      setStatus(next);
    } catch {
      if (requestGen.current === gen && selectedRef.current === repoId) {
        setError("Could not rebuild the index.");
      }
    }
  }

  async function onToggleWatch() {
    if (!selectedId || !status) {
      return;
    }
    const repoId = selectedId;
    const gen = requestGen.current;
    setError(null);
    try {
      const next = await client.setWatch(repoId, !status.watchEnabled);
      if (requestGen.current !== gen || selectedRef.current !== repoId) {
        return;
      }
      setStatus(next);
    } catch {
      if (requestGen.current === gen && selectedRef.current === repoId) {
        setError("Could not update the index watcher.");
      }
    }
  }

  async function onSearch() {
    if (!selectedId) {
      return;
    }
    const repoId = selectedId;
    const gen = requestGen.current;
    setError(null);
    try {
      const next = await client.search(repoId, query);
      if (requestGen.current !== gen || selectedRef.current !== repoId) {
        return;
      }
      setHits(next);
    } catch {
      if (requestGen.current === gen && selectedRef.current === repoId) {
        setError("Could not search the index.");
      }
    }
  }

  return (
    <section className="index-page">
      <p className="page-kicker">Index</p>
      <h1 className="page-title">Index</h1>
      <p className="page-body">
        Isolated sparse, dense, and graph retrieval per enrolled repository. Vectors stay
        disposable; missing embedding files degrade without blocking search.
      </p>
      {repositories.length ? (
        <label className="index-page__field" htmlFor="index-repo">
          Repository
          <select
            id="index-repo"
            value={selectedId}
            onChange={(event) => {
              selectRepository(event.target.value);
            }}
          >
            {repositories.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.displayName}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="index-page__empty">Enrol a repository before building an index.</p>
      )}
      {status ? (
        <dl className="index-page__status">
          <div>
            <dt>State</dt>
            <dd>{status.state}</dd>
          </div>
          <div>
            <dt>Files</dt>
            <dd>
              {status.filesDone} / {status.filesTotal}
            </dd>
          </div>
          <div>
            <dt>Chunks embedded</dt>
            <dd>{status.chunksEmbedded}</dd>
          </div>
          <div>
            <dt>Chunks skipped</dt>
            <dd>{status.chunksSkipped}</dd>
          </div>
          <div>
            <dt>Chunk count</dt>
            <dd>{status.chunkCount}</dd>
          </div>
          <div>
            <dt>Commit</dt>
            <dd>{status.commit ?? "none"}</dd>
          </div>
          <div>
            <dt>Dense</dt>
            <dd>{status.denseAvailable ? "dense available" : "dense unavailable"}</dd>
          </div>
          <div>
            <dt>Last activity</dt>
            <dd>{status.lastActivityAt ?? "none"}</dd>
          </div>
        </dl>
      ) : null}
      {status ? (
        <label className="index-page__watch">
          <input
            type="checkbox"
            checked={status.watchEnabled}
            onChange={() => {
              void onToggleWatch();
            }}
          />
          Watch working tree
        </label>
      ) : null}
      <div className="index-page__actions">
        <button type="button" className="btn-quiet" onClick={() => void onRebuild()}>
          Rebuild index
        </button>
      </div>
      <form
        className="index-page__search"
        onSubmit={(event) => {
          event.preventDefault();
          void onSearch();
        }}
      >
        <label className="index-page__field" htmlFor="index-query">
          Search index
          <input
            id="index-query"
            type="search"
            role="searchbox"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
          />
        </label>
        <button type="submit" className="btn-primary">
          Search
        </button>
      </form>
      {hits.length ? (
        <ul className="index-page__hits">
          {hits.map((hit) => (
            <li key={`${hit.path}:${hit.startLine}`}>
              <p className="index-page__hit-path">{hit.path}</p>
              <p className="index-page__hit-meta">
                {hit.startLine}-{hit.endLine} · {hit.rankSources.join(", ")} · {hit.trust}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
      {error ? <p className="wizard__error">{error}</p> : null}
    </section>
  );
}
