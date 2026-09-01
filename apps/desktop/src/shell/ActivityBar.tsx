// SPDX-License-Identifier: AGPL-3.0-or-later

export type ActivityId = "chat" | "workspaces" | "files" | "settings";

interface ActivityBarProps {
  active: ActivityId;
  collapsed?: boolean;
  onSelect: (id: ActivityId) => void;
}

const ITEMS: { id: ActivityId; label: string; icon: string }[] = [
  { id: "chat", label: "Chat", icon: "M4 5h16v10H7l-3 3z" },
  { id: "workspaces", label: "Workspaces", icon: "M4 6h7v12H4zM13 6h7v5h-7zM13 13h7v5h-7z" },
  { id: "files", label: "Files", icon: "M4 7h6l2 2h8v9H4z" },
];

export function ActivityBar({ active, collapsed = false, onSelect }: ActivityBarProps) {
  return (
    <nav className="activity-bar" aria-label="Activity" hidden={collapsed}>
      {ITEMS.map((item) => (
        <button
          key={item.id}
          type="button"
          className="activity-bar__btn"
          aria-label={item.label}
          aria-current={active === item.id ? "page" : undefined}
          onClick={() => {
            onSelect(item.id);
          }}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" className="activity-bar__icon">
            <path d={item.icon} fill="none" stroke="currentColor" strokeWidth="1.6" />
          </svg>
        </button>
      ))}
      <button
        type="button"
        className="activity-bar__btn activity-bar__btn--foot"
        aria-label="Settings"
        aria-current={active === "settings" ? "page" : undefined}
        onClick={() => {
          onSelect("settings");
        }}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className="activity-bar__icon">
          <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path
            d="M12 3v2.2M12 18.8V21M4.9 6.5l1.6 1.6M17.5 16l1.6 1.6M3 12h2.2M18.8 12H21M4.9 17.5l1.6-1.6M17.5 8.1l1.6-1.6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          />
        </svg>
      </button>
    </nav>
  );
}
