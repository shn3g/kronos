// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useId, useState, type ReactNode } from "react";
import { SAVE_FILE_EVENT } from "../features/files/fileEditor";

export type MenuId = "file" | "edit" | "view" | "help" | null;

interface MenuBarProps {
  historyOpen: boolean;
  activityCollapsed: boolean;
  inspectorCollapsed: boolean;
  terminalOpen: boolean;
  onNewChat: () => void;
  onOpenWorkspace: () => void;
  onToggleHistory: () => void;
  onToggleActivityBar: () => void;
  onToggleInspector: () => void;
  onToggleTerminal: () => void;
  onOpenSettings: () => void;
  onOpenModels: () => void;
}

export function MenuBar({
  historyOpen,
  activityCollapsed,
  inspectorCollapsed,
  terminalOpen,
  onNewChat,
  onOpenWorkspace,
  onToggleHistory,
  onToggleActivityBar,
  onToggleInspector,
  onToggleTerminal,
  onOpenSettings,
  onOpenModels,
}: MenuBarProps) {
  const [open, setOpen] = useState<MenuId>(null);
  const fileId = useId();
  const editId = useId();
  const viewId = useId();
  const helpId = useId();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="menu-bar" role="menubar" aria-label="Application">
      <Menu
        id={fileId}
        label="File"
        open={open === "file"}
        onOpen={() => {
          setOpen(open === "file" ? null : "file");
        }}
      >
        <MenuItem
          label="New chat"
          onSelect={() => {
            setOpen(null);
            onNewChat();
          }}
        />
        <MenuItem
          label="Open workspace"
          onSelect={() => {
            setOpen(null);
            onOpenWorkspace();
          }}
        />
        <MenuItem
          label="Save"
          onSelect={() => {
            setOpen(null);
            window.dispatchEvent(new Event(SAVE_FILE_EVENT));
          }}
        />
        <MenuItem
          label="Models"
          onSelect={() => {
            setOpen(null);
            onOpenModels();
          }}
        />
        <MenuItem
          label="Settings"
          onSelect={() => {
            setOpen(null);
            onOpenSettings();
          }}
        />
      </Menu>
      <Menu
        id={editId}
        label="Edit"
        open={open === "edit"}
        onOpen={() => {
          setOpen(open === "edit" ? null : "edit");
        }}
      >
        <MenuItem
          label="Cut"
          onSelect={() => {
            setOpen(null);
            runEditCommand("cut");
          }}
        />
        <MenuItem
          label="Copy"
          onSelect={() => {
            setOpen(null);
            runEditCommand("copy");
          }}
        />
        <MenuItem
          label="Paste"
          onSelect={() => {
            setOpen(null);
            runEditCommand("paste");
          }}
        />
        <MenuItem
          label="Select all"
          onSelect={() => {
            setOpen(null);
            runEditCommand("selectAll");
          }}
        />
      </Menu>
      <Menu
        id={viewId}
        label="View"
        open={open === "view"}
        onOpen={() => {
          setOpen(open === "view" ? null : "view");
        }}
      >
        <MenuItem
          label={historyOpen ? "Hide chat history" : "Chat history"}
          onSelect={() => {
            setOpen(null);
            onToggleHistory();
          }}
        />
        <MenuItem
          label={activityCollapsed ? "Show activity bar" : "Hide activity bar"}
          onSelect={() => {
            setOpen(null);
            onToggleActivityBar();
          }}
        />
        <MenuItem
          label={inspectorCollapsed ? "Show inspector" : "Hide inspector"}
          onSelect={() => {
            setOpen(null);
            onToggleInspector();
          }}
        />
        <MenuItem
          label={terminalOpen ? "Hide terminal" : "Terminal"}
          onSelect={() => {
            setOpen(null);
            onToggleTerminal();
          }}
        />
      </Menu>
      <Menu
        id={helpId}
        label="Help"
        open={open === "help"}
        onOpen={() => {
          setOpen(open === "help" ? null : "help");
        }}
      >
        <p className="menu-help">
          Kronos is a locally installed desktop app for coding agents on your git folders. Ctrl+N
          or Cmd+N starts a new chat. Ctrl+B or Cmd+B hides the activity bar. Ctrl+Shift+J or
          Cmd+Shift+J hides Changes. Ctrl+` or Cmd+` shows Terminal. In Terminal, the shell stays
          open. Type a line and press Enter. Up and Down recall previous lines. Stop, or Escape in
          the command box, ends the shell. Escape also
          stops the current chat turn.
          Revert in Changes restores the last chat write for that file, or the last committed
          version if chat did not write it. Commit records a local git commit. This turn lists
          files chat wrote. All lists every dirty file. Kronos does not push. AGENTS.md,
          .cursorrules, and files under .cursor/rules are followed on every chat turn. Apply on a
          code block writes that file into the open folder and lists it in Changes. Retry
          sends the last prompt again. Try again resends after a failed send. Click a file mention
          in chat, or Open in Changes, to edit that file in Files. Save or Ctrl+S writes it into
          the folder.
        </p>
      </Menu>
    </div>
  );
}

interface MenuProps {
  id: string;
  label: string;
  open: boolean;
  onOpen: () => void;
  children: ReactNode;
}

function Menu({ id, label, open, onOpen, children }: MenuProps) {
  return (
    <div className="menu">
      <button
        type="button"
        className="menu__trigger"
        role="menuitem"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={id}
        onClick={onOpen}
      >
        {label}
      </button>
      {open ? (
        <div className="menu__panel" id={id} role="menu">
          {children}
        </div>
      ) : null}
    </div>
  );
}

interface MenuItemProps {
  label: string;
  onSelect: () => void;
}

function MenuItem({ label, onSelect }: MenuItemProps) {
  return (
    <button type="button" className="menu__item" role="menuitem" onClick={onSelect}>
      {label}
    </button>
  );
}

function runEditCommand(command: "cut" | "copy" | "paste" | "selectAll"): void {
  try {
    document.execCommand(command);
  } catch {
    return;
  }
}
