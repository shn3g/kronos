// SPDX-License-Identifier: AGPL-3.0-or-later

interface ChatPathButtonProps {
  path: string;
  onOpen: (path: string) => void;
}

export function ChatPathButton({ path, onOpen }: ChatPathButtonProps) {
  return (
    <button
      type="button"
      className="chat-path"
      aria-label={`Open ${path}`}
      onClick={() => {
        onOpen(path);
      }}
    >
      <code>{path}</code>
    </button>
  );
}
