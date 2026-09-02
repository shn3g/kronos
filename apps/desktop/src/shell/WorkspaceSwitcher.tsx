// SPDX-License-Identifier: AGPL-3.0-or-later

import type { EnrolledRepository } from "../features/workspaces/client";

interface WorkspaceSwitcherProps {
  repositories: EnrolledRepository[];
  workspaceId: string | null;
  onChange: (id: string | null) => void;
  onOpenFolder: () => void;
}

export function WorkspaceSwitcher({
  repositories,
  workspaceId,
  onChange,
  onOpenFolder,
}: WorkspaceSwitcherProps) {
  const active = repositories.filter((item) => item.status === "active");
  return (
    <div className="title-bar__workspace-group">
      <label className="title-bar__workspace">
        <span className="visually-hidden">Workspace</span>
        <select
          aria-label="Workspace"
          value={workspaceId ?? ""}
          onChange={(event) => {
            const next = event.target.value;
            onChange(next === "" ? null : next);
          }}
        >
          <option value="">No workspace</option>
          {active.map((item) => (
            <option key={item.id} value={item.id}>
              {item.displayName}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="btn-quiet" onClick={onOpenFolder}>
        Open folder
      </button>
    </div>
  );
}
