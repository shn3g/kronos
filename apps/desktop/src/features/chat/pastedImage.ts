// SPDX-License-Identifier: AGPL-3.0-or-later

export const ALLOWED_CHAT_IMAGE_MIMES = ["image/png", "image/jpeg", "image/webp", "image/gif"] as const;
export const MAX_CHAT_IMAGE_BYTES = 2 * 1024 * 1024;
export const MAX_CHAT_IMAGES_PER_TURN = 3;

export type AllowedChatImageMime = (typeof ALLOWED_CHAT_IMAGE_MIMES)[number];

export interface ChatComposerImage {
  id: string;
  mime: AllowedChatImageMime;
  data: string;
  previewUrl: string;
}

export type PastedImageFailure = "type" | "size" | "limit";

const MARKER = /!\[Pasted image\]\(kronos-image:([A-Za-z0-9_-]+)\)/g;

export function isAllowedChatImageMime(mime: string): mime is AllowedChatImageMime {
  return (ALLOWED_CHAT_IMAGE_MIMES as readonly string[]).includes(mime);
}

export function pastedImageError(reason: PastedImageFailure): string {
  if (reason === "type") {
    return "Kronos can only paste png, jpeg, webp, or gif images.";
  }
  if (reason === "size") {
    return "That image is too large. Use a file under 2 MB.";
  }
  return "You can paste up to 3 images in one message.";
}

export function dataUrlForChatImage(mime: string, data: string): string {
  return `data:${mime};base64,${data}`;
}

export async function readPastedImageFile(
  file: File,
): Promise<{ ok: true; mime: AllowedChatImageMime; data: string } | { ok: false; reason: "type" | "size" }> {
  if (!isAllowedChatImageMime(file.type)) {
    return { ok: false, reason: "type" };
  }
  const bytes = await readFileBytes(file);
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_CHAT_IMAGE_BYTES) {
    return { ok: false, reason: "size" };
  }
  return { ok: true, mime: file.type, data: bytesToBase64(bytes) };
}

export function imageFilesFromClipboard(data: DataTransfer | null): File[] {
  if (!data || !data.files) {
    return [];
  }
  return Array.from(data.files).filter((file) => isAllowedChatImageMime(file.type));
}

export function clipboardHasFiles(data: DataTransfer | null): boolean {
  if (!data || !data.files) {
    return false;
  }
  return data.files.length > 0;
}

export function chatImageIdsInText(content: string): string[] {
  return [...content.matchAll(MARKER)].flatMap((match) => {
    const id = match[1];
    return id === undefined || id === "" ? [] : [id];
  });
}

export function userMessageSegments(content: string): Array<{ kind: "text" | "image"; value: string }> {
  const segments: Array<{ kind: "text" | "image"; value: string }> = [];
  let cursor = 0;
  for (const match of content.matchAll(MARKER)) {
    const index = match.index ?? 0;
    const id = match[1];
    if (id === undefined) {
      continue;
    }
    if (index > cursor) {
      segments.push({ kind: "text", value: content.slice(cursor, index) });
    }
    segments.push({ kind: "image", value: id });
    cursor = index + match[0].length;
  }
  if (cursor < content.length) {
    segments.push({ kind: "text", value: content.slice(cursor) });
  }
  return segments;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
  }
  return btoa(binary);
}

async function readFileBytes(file: Blob): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === "function") {
    return new Uint8Array(await file.arrayBuffer());
  }
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (!(reader.result instanceof ArrayBuffer)) {
        reject(new Error("Could not read that image."));
        return;
      }
      resolve(new Uint8Array(reader.result));
    };
    reader.onerror = () => {
      reject(reader.error ?? new Error("Could not read that image."));
    };
    reader.readAsArrayBuffer(file);
  });
}
