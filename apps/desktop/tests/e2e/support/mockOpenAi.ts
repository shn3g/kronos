// SPDX-License-Identifier: AGPL-3.0-or-later

import { createServer, type Server } from "node:http";

export const E2E_MOCK_PORT = 18766;
export const E2E_ENGINE_PORT = 18765;
export const E2E_AUTH_TOKEN = "e2e-with-engine-token";
export const E2E_README_BODY = "# hello kronos\n";
export const E2E_FINAL_ANSWER = "README.md starts with hello kronos.";

export function readFileToolFence(path: string): string {
  return ["```tool", JSON.stringify({ name: "read_file", path }), "```"].join("\n");
}

export function scriptedAssistantText(completionIndex: number): string {
  if (completionIndex === 0) {
    return readFileToolFence("README.md");
  }
  return E2E_FINAL_ANSWER;
}

export function openaiChatSse(text: string): string {
  return `data: ${JSON.stringify({ choices: [{ delta: { content: text } }] })}\n\n` + "data: [DONE]\n\n";
}

export function startMockOpenAiServer(port: number = E2E_MOCK_PORT): Promise<{
  url: string;
  close: () => Promise<void>;
}> {
  let completions = 0;
  const server: Server = createServer((req, res) => {
    const url = req.url ?? "";
    if (req.method === "GET" && (url === "/v1/models" || url.startsWith("/v1/models?"))) {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ data: [{ id: "mock" }] }));
      return;
    }
    if (req.method === "POST" && url.includes("chat/completions")) {
      const chunks: Buffer[] = [];
      req.on("data", (chunk: Buffer) => {
        chunks.push(chunk);
      });
      req.on("end", () => {
        const text = scriptedAssistantText(completions);
        completions += 1;
        res.writeHead(200, { "content-type": "text/event-stream; charset=utf-8" });
        res.end(openaiChatSse(text));
      });
      return;
    }
    res.writeHead(404);
    res.end();
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      resolve({
        url: `http://127.0.0.1:${port}/v1`,
        close: () =>
          new Promise((done, fail) => {
            server.close((error) => {
              if (error) {
                fail(error);
                return;
              }
              done();
            });
          }),
      });
    });
  });
}
