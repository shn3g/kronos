// SPDX-License-Identifier: AGPL-3.0-or-later

export const EDITOR_HIGHLIGHT_CHAR_LIMIT = 100_000;

export type EditorLanguage =
  | "python"
  | "javascript"
  | "typescript"
  | "json"
  | "css"
  | "html"
  | "markdown"
  | "rust"
  | "go"
  | "shell"
  | "yaml"
  | "toml";

export type EditorHighlightKind = "plain" | "keyword" | "string" | "comment" | "number";

export interface EditorHighlightToken {
  kind: EditorHighlightKind;
  text: string;
}

const LANGUAGE_BY_EXTENSION: Record<string, EditorLanguage> = {
  py: "python",
  pyi: "python",
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  json: "json",
  css: "css",
  scss: "css",
  html: "html",
  htm: "html",
  md: "markdown",
  mdx: "markdown",
  rs: "rust",
  go: "go",
  sh: "shell",
  bash: "shell",
  zsh: "shell",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
};

export function editorLanguageFromPath(path: string): EditorLanguage | null {
  const base = path.replaceAll("\\", "/").trim().split("/").pop() ?? "";
  const lower = base.toLowerCase();
  if (lower.endsWith(".d.ts")) {
    return "typescript";
  }
  const dot = lower.lastIndexOf(".");
  if (dot < 0 || dot === lower.length - 1) {
    return null;
  }
  return LANGUAGE_BY_EXTENSION[lower.slice(dot + 1)] ?? null;
}

export function highlightEditorTokens(
  content: string,
  language: EditorLanguage,
): EditorHighlightToken[] {
  if (content.length > EDITOR_HIGHLIGHT_CHAR_LIMIT) {
    return [{ kind: "plain", text: content }];
  }
  const syntax = syntaxFor(language);
  const tokens: EditorHighlightToken[] = [];
  let index = 0;
  while (index < content.length) {
    const block = matchBlockComment(content, index, syntax.blockComments);
    if (block !== null) {
      appendToken(tokens, "comment", block);
      index += block.length;
      continue;
    }
    const line = matchLineComment(content, index, syntax.lineComments);
    if (line !== null) {
      appendToken(tokens, "comment", line);
      index += line.length;
      continue;
    }
    const quoted = matchQuoted(content, index, syntax.strings);
    if (quoted !== null) {
      appendToken(tokens, "string", quoted);
      index += quoted.length;
      continue;
    }
    const number = matchNumber(content, index);
    if (number !== null) {
      appendToken(tokens, "number", number);
      index += number.length;
      continue;
    }
    const ident = matchIdent(content, index);
    if (ident !== null) {
      appendToken(tokens, syntax.keywords.has(ident) ? "keyword" : "plain", ident);
      index += ident.length;
      continue;
    }
    appendToken(tokens, "plain", content[index] ?? "");
    index += 1;
  }
  return tokens;
}

interface LanguageSyntax {
  keywords: ReadonlySet<string>;
  lineComments: readonly string[];
  blockComments: readonly [string, string][];
  strings: readonly string[];
}

function syntaxFor(language: EditorLanguage): LanguageSyntax {
  switch (language) {
    case "python":
      return {
        keywords: words(
          "def class return if else elif for while import from as try except finally with yield lambda pass break continue True False None and or not in is async await",
        ),
        lineComments: ["#"],
        blockComments: [],
        strings: ['"""', "'''", '"', "'"],
      };
    case "javascript":
    case "typescript":
      return {
        keywords: words(
          language === "typescript"
            ? `${JS_KEYWORDS} type interface extends implements public private protected readonly enum satisfies`
            : JS_KEYWORDS,
        ),
        lineComments: ["//"],
        blockComments: [["/*", "*/"]],
        strings: ["`", '"', "'"],
      };
    case "json":
      return { keywords: words("true false null"), lineComments: [], blockComments: [], strings: ['"'] };
    case "css":
      return { keywords: words(""), lineComments: [], blockComments: [["/*", "*/"]], strings: ['"', "'"] };
    case "html":
      return { keywords: words(""), lineComments: [], blockComments: [["<!--", "-->"]], strings: ['"', "'"] };
    case "markdown":
      return { keywords: words(""), lineComments: [], blockComments: [], strings: ["```", "`"] };
    case "rust":
      return {
        keywords: words(
          "fn let mut pub struct enum impl trait use mod return if else match for while loop crate self Self async await type const static where move ref true false",
        ),
        lineComments: ["//"],
        blockComments: [["/*", "*/"]],
        strings: ['"', "'"],
      };
    case "go":
      return {
        keywords: words(
          "func package import return if else for range struct type map chan var const defer go select case switch break continue fallthrough interface true false nil",
        ),
        lineComments: ["//"],
        blockComments: [["/*", "*/"]],
        strings: ["`", '"', "'"],
      };
    case "shell":
      return {
        keywords: words("if then else fi for in do done case esac function return exit"),
        lineComments: ["#"],
        blockComments: [],
        strings: ['"', "'"],
      };
    case "yaml":
    case "toml":
      return { keywords: words("true false null"), lineComments: ["#"], blockComments: [], strings: ['"', "'"] };
  }
}

const JS_KEYWORDS =
  "const let var function return if else for while do class import from export default async await new this try catch finally throw switch case break continue of in typeof instanceof void yield true false null undefined debugger super static";

function words(source: string): Set<string> {
  return new Set(source.split(" ").filter((item) => item !== ""));
}

function appendToken(
  tokens: EditorHighlightToken[],
  kind: EditorHighlightKind,
  text: string,
): void {
  if (text === "") {
    return;
  }
  const last = tokens[tokens.length - 1];
  if (last !== undefined && last.kind === kind) {
    tokens[tokens.length - 1] = { kind, text: `${last.text}${text}` };
    return;
  }
  tokens.push({ kind, text });
}

function matchBlockComment(
  content: string,
  index: number,
  blocks: readonly [string, string][],
): string | null {
  for (const [open, close] of blocks) {
    if (!content.startsWith(open, index)) {
      continue;
    }
    const end = content.indexOf(close, index + open.length);
    if (end < 0) {
      return content.slice(index);
    }
    return content.slice(index, end + close.length);
  }
  return null;
}

function matchLineComment(content: string, index: number, markers: readonly string[]): string | null {
  const marker = markers.find((item) => content.startsWith(item, index));
  if (marker === undefined) {
    return null;
  }
  const newline = content.indexOf("\n", index);
  if (newline < 0) {
    return content.slice(index);
  }
  return content.slice(index, newline + 1);
}

function matchQuoted(content: string, index: number, openers: readonly string[]): string | null {
  const opener = openers.find((item) => content.startsWith(item, index));
  if (opener === undefined) {
    return null;
  }
  let cursor = index + opener.length;
  while (cursor < content.length) {
    if (content[cursor] === "\\" && cursor + 1 < content.length) {
      cursor += 2;
      continue;
    }
    if (content.startsWith(opener, cursor)) {
      return content.slice(index, cursor + opener.length);
    }
    cursor += 1;
  }
  return content.slice(index);
}

function matchNumber(content: string, index: number): string | null {
  const head = content[index];
  if (head === undefined || head < "0" || head > "9") {
    return null;
  }
  let cursor = index + 1;
  while (cursor < content.length && content[cursor]! >= "0" && content[cursor]! <= "9") {
    cursor += 1;
  }
  if (content[cursor] === "." && content[cursor + 1] !== undefined && content[cursor + 1]! >= "0" && content[cursor + 1]! <= "9") {
    cursor += 2;
    while (cursor < content.length && content[cursor]! >= "0" && content[cursor]! <= "9") {
      cursor += 1;
    }
  }
  return content.slice(index, cursor);
}

function matchIdent(content: string, index: number): string | null {
  const head = content[index];
  if (head === undefined || !isIdentStart(head)) {
    return null;
  }
  let cursor = index + 1;
  while (cursor < content.length && isIdentPart(content[cursor] ?? "")) {
    cursor += 1;
  }
  return content.slice(index, cursor);
}

function isIdentStart(char: string): boolean {
  return (char >= "A" && char <= "Z") || (char >= "a" && char <= "z") || char === "_";
}

function isIdentPart(char: string): boolean {
  return isIdentStart(char) || (char >= "0" && char <= "9");
}
