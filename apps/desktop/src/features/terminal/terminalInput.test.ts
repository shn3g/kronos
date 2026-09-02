import { describe, expect, it } from "vitest";
import { ptyInputFromKeyboard, xtermCanvasIsUsable } from "./terminalInput";

describe("ptyInputFromKeyboard", () => {
  it("sends printable keys and maps Enter to carriage return", () => {
    expect(ptyInputFromKeyboard({ key: "e", ctrlKey: false, metaKey: false, altKey: false })).toBe("e");
    expect(ptyInputFromKeyboard({ key: "Enter", ctrlKey: false, metaKey: false, altKey: false })).toBe(
      "\r",
    );
    expect(ptyInputFromKeyboard({ key: "Backspace", ctrlKey: false, metaKey: false, altKey: false })).toBe(
      "\x7f",
    );
  });

  it("sends Ctrl+C as interrupt and ignores lone modifiers", () => {
    expect(ptyInputFromKeyboard({ key: "c", ctrlKey: true, metaKey: false, altKey: false })).toBe("\x03");
    expect(ptyInputFromKeyboard({ key: "Control", ctrlKey: true, metaKey: false, altKey: false })).toBeNull();
    expect(ptyInputFromKeyboard({ key: "ArrowUp", ctrlKey: false, metaKey: false, altKey: false })).toBe(
      "\x1b[A",
    );
  });
});

describe("xtermCanvasIsUsable", () => {
  it("does not start xterm when the document cannot draw", () => {
    expect(xtermCanvasIsUsable()).toBe(false);
  });
});
