// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useId, useState, type ReactNode } from "react";
import { SAVE_FILE_EVENT } from "../features/files/fileEditor";
import { KEYBOARD_SHORTCUTS } from "./keyboardHelp";

export type MenuId = "file" | "edit" | "view" | "help" | null;

interface MenuBarProps {
  historyOpen: boolean;
  activityCollapsed: boolean;
  inspectorCollapsed: boolean;
  terminalOpen: boolean;
  onNewChat: () => void;
  onOpenFolder: () => void;
  onGoToFile: () => void;
  onFindInFile: () => void;
  onFindInFiles: () => void;
  onReplaceInFile: () => void;
  onGoToLine: () => void;
  onAskInChat: () => void;
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
  onOpenFolder,
  onGoToFile,
  onFindInFile,
  onFindInFiles,
  onReplaceInFile,
  onGoToLine,
  onAskInChat,
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
    <div className="menu-bar" id="menu-bar" role="menubar" aria-label="Application">
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
          label="Open Folder"
          onSelect={() => {
            setOpen(null);
            onOpenFolder();
          }}
        />
        <MenuItem
          label="Go to file"
          onSelect={() => {
            setOpen(null);
            onGoToFile();
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
        <MenuItem
          label="Ask in chat"
          onSelect={() => {
            setOpen(null);
            onAskInChat();
          }}
        />
        <MenuItem
          label="Find"
          onSelect={() => {
            setOpen(null);
            onFindInFile();
          }}
        />
        <MenuItem
          label="Find in files"
          onSelect={() => {
            setOpen(null);
            onFindInFiles();
          }}
        />
        <MenuItem
          label="Replace"
          onSelect={() => {
            setOpen(null);
            onReplaceInFile();
          }}
        />
        <MenuItem
          label="Go to line"
          onSelect={() => {
            setOpen(null);
            onGoToLine();
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
        <ul className="menu-help" aria-label="Keyboard shortcuts">
          {KEYBOARD_SHORTCUTS.map((row) => (
            <li key={row.action} className="menu-help__row">
              <kbd className="menu-help__shortcut">{row.shortcut}</kbd>
              <span className="menu-help__action">{row.action}</span>
            </li>
          ))}
        </ul>
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
