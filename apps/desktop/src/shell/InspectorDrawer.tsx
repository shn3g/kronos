// SPDX-License-Identifier: AGPL-3.0-or-later

import type { HealthCheck } from "../features/health/checks";
import { HealthList } from "../features/health/HealthList";

export type InspectorTab = "changes" | "goals" | "health";

export interface InspectorChange {
  path: string;
  summary: string;
}

interface InspectorDrawerProps {
  tab: InspectorTab;
  onTab: (tab: InspectorTab) => void;
  changes: InspectorChange[];
  goals: { id: string; title: string; state: string }[];
  checks: HealthCheck[];
}

export function InspectorDrawer({ tab, onTab, changes, goals, checks }: InspectorDrawerProps) {
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
            <ul className="inspector__list">
              {changes.map((item) => (
                <li key={`${item.path}:${item.summary}`}>
                  <strong>{item.path}</strong>
                  <span>{item.summary}</span>
                </li>
              ))}
            </ul>
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
