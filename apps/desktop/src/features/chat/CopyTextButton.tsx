// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from "react";
import { writeClipboardText } from "./writeClipboardText";

interface CopyTextButtonProps {
  text: string;
  idleLabel: string;
}

export function CopyTextButton({ text, idleLabel }: CopyTextButtonProps) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");

  async function onCopy(): Promise<void> {
    const ok = await writeClipboardText(text);
    setState(ok ? "copied" : "error");
  }

  return (
    <span className="copy-text">
      <button type="button" className="copy-text__btn" onClick={() => void onCopy()}>
        {state === "copied" ? "Copied" : idleLabel}
      </button>
      {state === "error" ? (
        <p className="copy-text__error" role="status">
          Could not copy. Select the text and copy it yourself.
        </p>
      ) : null}
    </span>
  );
}
