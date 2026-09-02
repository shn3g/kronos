// SPDX-License-Identifier: AGPL-3.0-or-later

import type { IncomingMessage, ServerResponse } from "node:http";
import http from "node:http";
import type { Plugin } from "vite";
import { DESKTOP_CLIENT_VERSION } from "../api/kronosClient";
import { kronosConfigDir, readWebEngineBinding } from "./webEngineBinding";

const PREFIX = "/kronos-engine";

export function webEngineProxyPlugin(): Plugin {
  return {
    name: "kronos-web-engine-proxy",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? "";
        if (!url.startsWith(PREFIX)) {
          next();
          return;
        }
        const binding = readWebEngineBinding(kronosConfigDir());
        if (!binding) {
          res.statusCode = 503;
          res.end();
          return;
        }
        proxyToEngine(req, res, binding, url.slice(PREFIX.length) || "/");
      });
    },
  };
}

function proxyToEngine(
  req: IncomingMessage,
  res: ServerResponse,
  binding: { baseUrl: string; token: string },
  enginePath: string,
): void {
  const target = new URL(enginePath, `${binding.baseUrl.replace(/\/$/, "")}/`);
  const chunks: Buffer[] = [];
  req.on("data", (chunk: Buffer) => {
    chunks.push(chunk);
  });
  req.on("end", () => {
    const payload = Buffer.concat(chunks);
    const headers: Record<string, string> = {
      authorization: `Bearer ${binding.token}`,
      "x-kronos-client-version": DESKTOP_CLIENT_VERSION,
    };
    const contentType = req.headers["content-type"];
    if (typeof contentType === "string") {
      headers["content-type"] = contentType;
    }
    const upstream = http.request(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port,
        path: `${target.pathname}${target.search}`,
        method: req.method,
        headers,
      },
      (incoming) => {
        res.statusCode = incoming.statusCode ?? 502;
        const type = incoming.headers["content-type"];
        if (typeof type === "string") {
          res.setHeader("Content-Type", type);
        }
        incoming.pipe(res);
      },
    );
    upstream.on("error", () => {
      if (!res.headersSent) {
        res.statusCode = 503;
      }
      res.end();
    });
    if (payload.length > 0) {
      upstream.write(payload);
    }
    upstream.end();
  });
}
