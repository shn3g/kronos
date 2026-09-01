// SPDX-License-Identifier: AGPL-3.0-or-later

export interface TerminalKeyEvent {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

export function ptyInputFromKeyboard(event: TerminalKeyEvent): string | null {
  if (event.altKey || event.metaKey) {
    return null;
  }
  if (event.key === "Control" || event.key === "Shift" || event.key === "Alt" || event.key === "Meta") {
    return null;
  }
  if (event.ctrlKey) {
    const letter = event.key.length === 1 ? event.key.toLowerCase() : "";
    if (letter === "c") {
      return "\x03";
    }
    if (letter === "d") {
      return "\x04";
    }
    if (letter === "z") {
      return "\x1a";
    }
    return null;
  }
  if (event.key === "Enter") {
    return "\r";
  }
  if (event.key === "Backspace") {
    return "\x7f";
  }
  if (event.key === "Tab") {
    return "\t";
  }
  if (event.key === "Escape") {
    return "\x1b";
  }
  if (event.key === "ArrowUp") {
    return "\x1b[A";
  }
  if (event.key === "ArrowDown") {
    return "\x1b[B";
  }
  if (event.key === "ArrowRight") {
    return "\x1b[C";
  }
  if (event.key === "ArrowLeft") {
    return "\x1b[D";
  }
  if (event.key === "Home") {
    return "\x1b[H";
  }
  if (event.key === "End") {
    return "\x1b[F";
  }
  if (event.key === "Delete") {
    return "\x1b[3~";
  }
  if (event.key.length === 1) {
    return event.key;
  }
  return null;
}

export function xtermCanvasIsUsable(): boolean {
  if (typeof document === "undefined" || typeof HTMLCanvasElement === "undefined") {
    return false;
  }
  if (typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent)) {
    return false;
  }
  try {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    return context !== null && typeof context.fillRect === "function";
  } catch {
    return false;
  }
}
