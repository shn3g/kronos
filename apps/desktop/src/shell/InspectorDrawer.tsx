// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from "react";
import type { HealthCheck } from "../features/health/checks";
import { HealthList } from "../features/health/HealthList";

export type InspectorTab = "changes" | "goals" | "health";

export interface InspectorChange {
  path: string;
  summary: string;
  patch?: string;
}

interface InspectorDrawerProps {
  tab: InspectorTab;
  onTab: (tab: InspectorTab) => void;
  changes: InspectorChange[];
  goals: { id: string; title: string; state: string }[];
  checks: HealthCheck[];
  onRevert?: (path: string) => void;
  revertError?: string | null;
  revertingPath?: string | null;
}

export function InspectorDrawer({
  tab,
  onTab,
  changes,
  goals,
  checks,
  onRevert,
  revertError = null,
  revertingPath = null,
}: InspectorDrawerProps) {
  return (
    <aside className="inspector" aria-label="Session details">
      <div className="inspector__tabs" role="tablist" aria-label="Inspector">
        <TabButton selected={tab === "changes"} onClick={() => onTab("changes")}>
          Changes
        </TabButton>
        <TabButton selected={tab === "goals"} onClick={() => onTab("goals")}>
          Goals
        </TabButton>
        <TabButton selected={tab === "health"} onClick={() => onTab("health")}>
          Health
        </TabButton>
      </div>
      <div className="inspector__body" role="tabpanel">
        {tab === "changes" ? (
          changes.length === 0 ? (
            <p className="inspector__empty">No file changes in this workspace yet.</p>
          ) : (
            <>
              {revertError ? (
                <p className="inspector__error" role="alert">
                  {revertError}
                </p>
              ) : null}
              <ul className="inspector__list">
                {changes.map((item) => (
                  <ChangeRow
                    key={`${item.path}:${item.summary}`}
                    item={item}
                    onRevert={onRevert}
                    reverting={revertingPath === item.path}
                  />
                ))}
              </ul>
            </>
          )
        ) : null}
        {tab === "goals" ? (
          goals.length === 0 ? (
            <p className="inspector__empty">
              No goals yet. Ask chat to start one when the work should run unattended.
            </p>
          ) : (
            <ul className="inspector__list">
              {goals.map((item) => (
                <li key={item.id}>
                  <strong>{item.title}</strong>
                  <span>{item.state}</span>
                </li>
              ))}
            </ul>
          )
        ) : null}
        {tab === "health" ? <HealthList checks={checks} /> : null}
      </div>
    </aside>
  );
}

function ChangeRow({
  item,
  onRevert,
  reverting,
}: {
  item: InspectorChange;
  onRevert: ((path: string) => void) | undefined;
  reverting: boolean;
}) {
  const [open, setOpen] = useState(false);
  const patch = item.patch ?? "";
  return (
    <li>
      <div className="inspector__change-row">
        {patch === "" ? (
          <div className="inspector__change">
            <strong>{item.path}</strong>
            <span>{item.summary}</span>
          </div>
        ) : (
          <button
            type="button"
            className="inspector__change"
            aria-expanded={open}
            onClick={() => {
              setOpen((current) => !current);
            }}
          >
            <strong>{item.path}</strong>
            <span>{item.summary}</span>
          </button>
        )}
        {onRevert ? (
          <button
            type="button"
            className="btn-quiet"
            aria-label={`Revert ${item.path}`}
            disabled={reverting}
            onClick={() => {
              onRevert(item.path);
            }}
          >
            Revert
          </button>
        ) : null}
      </div>
      {open && patch !== "" ? <pre className="inspector__diff">{patch}</pre> : null}
    </li>
  );
}

interface TabButtonProps {
  selected: boolean;
  onClick: () => void;
  children: string;
}

function TabButton({ selected, onClick, children }: TabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      className="inspector__tab"
      onClick={onClick}
    >
      {children}
    </button>
  );
}
