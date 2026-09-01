// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from "react";
import type { HealthCheck } from "../features/health/checks";
import { HealthList } from "../features/health/HealthList";
import {
  visibleInspectorChanges,
  type ChangeListScope,
} from "./inspectWorkspaceChanges";

export type InspectorTab = "changes" | "goals" | "health";

export interface InspectorChange {
  path: string;
  summary: string;
  patch?: string;
  fromChat?: boolean;
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
  onCommit?: (message: string, paths: string[]) => void;
  commitError?: string | null;
  committing?: boolean;
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
  onCommit,
  commitError = null,
  committing = false,
}: InspectorDrawerProps) {
  const [pickedScope, setPickedScope] = useState<ChangeListScope | null>(null);
  const hasTurn = changes.some((item) => item.fromChat === true);
  const scope: ChangeListScope = pickedScope ?? (hasTurn ? "turn" : "all");
  const visible = visibleInspectorChanges(changes, scope);
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
              {revertError || commitError ? (
                <p className="inspector__error" role="alert">
                  {commitError ?? revertError}
                </p>
              ) : null}
              <div className="inspector__scope" role="radiogroup" aria-label="Change list">
                <ScopeButton
                  selected={scope === "turn"}
                  onClick={() => {
                    setPickedScope("turn");
                  }}
                >
                  This turn
                </ScopeButton>
                <ScopeButton
                  selected={scope === "all"}
                  onClick={() => {
                    setPickedScope("all");
                  }}
                >
                  All
                </ScopeButton>
              </div>
              {visible.length === 0 ? (
                <p className="inspector__empty">
                  No chat writes in the working tree. Choose All to see other edits.
                </p>
              ) : (
                <>
                  {onCommit ? (
                    <CommitForm
                      committing={committing}
                      onCommit={(message) => {
                        onCommit(
                          message,
                          visible.map((item) => item.path),
                        );
                      }}
                    />
                  ) : null}
                  <ul className="inspector__list">
                    {visible.map((item) => (
                      <ChangeRow
                        key={`${item.path}:${item.summary}`}
                        item={item}
                        onRevert={onRevert}
                        reverting={revertingPath === item.path}
                      />
                    ))}
                  </ul>
                </>
              )}
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

function CommitForm({
  committing,
  onCommit,
}: {
  committing: boolean;
  onCommit: (message: string) => void;
}) {
  const [message, setMessage] = useState("");
  return (
    <form
      className="inspector__commit"
      onSubmit={(event) => {
        event.preventDefault();
        const next = message.trim();
        if (next === "" || committing) {
          return;
        }
        onCommit(next);
      }}
    >
      <label>
        <span className="visually-hidden">Commit message</span>
        <textarea
          className="inspector__commit-input"
          value={message}
          rows={3}
          placeholder="Describe the change"
          aria-label="Commit message"
          onChange={(event) => {
            setMessage(event.target.value);
          }}
        />
      </label>
      <p className="inspector__hint">Records a local git commit. Kronos does not push.</p>
      <button
        type="submit"
        className="btn-primary"
        disabled={committing || message.trim() === ""}
      >
        {committing ? "Committing" : "Commit"}
      </button>
    </form>
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

function ScopeButton({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      className="inspector__scope-btn"
      onClick={onClick}
    >
      {children}
    </button>
  );
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
