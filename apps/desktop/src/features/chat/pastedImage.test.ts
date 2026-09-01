// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  MAX_CHAT_IMAGES_PER_TURN,
  chatImageIdsInText,
  imageFilesFromClipboard,
  pastedImageError,
  readPastedImageFile,
  userMessageSegments,
} from "./pastedImage";

const TINY_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

function pngFile(): File {
  const bytes = Uint8Array.from(atob(TINY_PNG_B64), (ch) => ch.charCodeAt(0));
  return new File([bytes], "shot.png", { type: "image/png" });
}

describe("readPastedImageFile", () => {
  it("accepts a small png", async () => {
    const result = await readPastedImageFile(pngFile());

    expect(result).toEqual({ ok: true, mime: "image/png", data: TINY_PNG_B64 });
  });

  it("rejects a non-image file and an oversized png", async () => {
    const text = await readPastedImageFile(new File(["hello"], "note.txt", { type: "text/plain" }));
    expect(text).toEqual({ ok: false, reason: "type" });
    expect(pastedImageError("type")).toMatch(/png, jpeg, webp, or gif/i);

    const huge = new File([new Uint8Array(2 * 1024 * 1024 + 8)], "big.png", { type: "image/png" });
    const size = await readPastedImageFile(huge);
    expect(size).toEqual({ ok: false, reason: "size" });
    expect(pastedImageError("size")).toMatch(/2 MB/i);
    expect(pastedImageError("limit")).toMatch(/3 images/i);
    expect(MAX_CHAT_IMAGES_PER_TURN).toBe(3);
  });
});

describe("imageFilesFromClipboard", () => {
  it("keeps image files and ignores other clipboard items", () => {
    const png = pngFile();
    const files = imageFilesFromClipboard({
      files: [png, new File(["x"], "note.txt", { type: "text/plain" })],
    } as unknown as DataTransfer);

    expect(files).toEqual([png]);
    expect(imageFilesFromClipboard(null)).toEqual([]);
  });
});

describe("userMessageSegments", () => {
  it("splits pasted-image markers from surrounding text", () => {
    const content = "Look\n![Pasted image](kronos-image:img_aaa)\nmore";

    expect(chatImageIdsInText(content)).toEqual(["img_aaa"]);
    expect(userMessageSegments(content)).toEqual([
      { kind: "text", value: "Look\n" },
      { kind: "image", value: "img_aaa" },
      { kind: "text", value: "\nmore" },
    ]);
  });
});
