/** @vitest-environment node */

import http from "node:http";
import { AddressInfo } from "node:net";
import { afterEach, describe, expect, it } from "vitest";
import { createProductionEngineClient } from "../engine/client";
import { pollEngineEvents } from "../features/engine/events";
import { DESKTOP_CLIENT_VERSION, probeEngineState } from "./kronosClient";

const servers: http.Server[] = [];

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map(
      (server) =>
        new Promise<void>((resolve, reject) => {
          server.close((error) => (error ? reject(error) : resolve()));
        }),
    ),
  );
});

async function serve(
  handler: (req: http.IncomingMessage, res: http.ServerResponse) => void,
): Promise<string> {
  const server = http.createServer(handler);
  servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  return `http://127.0.0.1:${address.port}`;
}

describe("probeEngineState", () => {
  it("does not send Authorization when token is empty", async () => {
    const baseUrl = await serve((req, res) => {
      if (req.url === "/health") {
        expect(req.headers.authorization).toBeUndefined();
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ status: "ok" }));
        return;
      }
      if (req.url === "/version") {
        expect(req.headers.authorization).toBeUndefined();
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            engine_version: DESKTOP_CLIENT_VERSION,
            min_client_version: "0.1.0",
            compatible: true,
          }),
        );
        return;
      }
      res.writeHead(404);
      res.end();
    });

    const state = await probeEngineState({
      baseUrl,
      token: "",
    });
    expect(state).toEqual({ status: "ready", version: DESKTOP_CLIENT_VERSION });
  });

  it("reports ready only when health is ok and versions are compatible", async () => {
    const baseUrl = await serve((req, res) => {
      if (req.url === "/health") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ status: "ok" }));
        return;
      }
      if (req.url === "/version") {
        expect(req.headers["x-kronos-client-version"]).toBe(DESKTOP_CLIENT_VERSION);
        expect(req.headers.authorization).toBe("Bearer install-token");
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            engine_version: DESKTOP_CLIENT_VERSION,
            min_client_version: "0.1.0",
            compatible: true,
          }),
        );
        return;
      }
      res.writeHead(404);
      res.end();
    });

    const state = await probeEngineState({
      baseUrl,
      token: "install-token",
    });
    expect(state).toEqual({ status: "ready", version: DESKTOP_CLIENT_VERSION });
  });

  it("reports incompatible version when the engine says the client is incompatible", async () => {
    const baseUrl = await serve((req, res) => {
      if (req.url === "/health") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ status: "ok" }));
        return;
      }
      if (req.url === "/version") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            engine_version: "2.0.0",
            min_client_version: "2.0.0",
            compatible: false,
          }),
        );
        return;
      }
      res.writeHead(404);
      res.end();
    });

    const state = await probeEngineState({
      baseUrl,
      token: "install-token",
    });
    expect(state).toEqual({
      status: "incompatible",
      clientVersion: DESKTOP_CLIENT_VERSION,
      engineVersion: "2.0.0",
    });
  });

  it("fails closed to unavailable when the loopback API is down", async () => {
    const state = await probeEngineState({
      baseUrl: "http://127.0.0.1:1",
      token: "install-token",
    });
    expect(state).toEqual({ status: "unavailable" });
  });
});

describe("createProductionEngineClient", () => {
  it("fails closed when the sidecar reports no state", async () => {
    const client = createProductionEngineClient({
      readState: async () => null,
    });
    const state = await client.getState();
    expect(state.status).toBe("unavailable");
    expect(state).not.toMatchObject({ status: "ready" });
  });

  it("uses sidecar probe state without a renderer bearer token", async () => {
    const client = createProductionEngineClient({
      readState: async () => ({ status: "ready", version: "0.1.0" }),
    });
    await expect(client.getState()).resolves.toEqual({
      status: "ready",
      version: "0.1.0",
    });
  });

  it("reports starting while the sidecar is coming up", async () => {
    const client = createProductionEngineClient({
      readState: async () => ({ status: "starting" }),
    });
    await expect(client.getState()).resolves.toEqual({ status: "starting" });
  });
});

describe("pollEngineEvents", () => {
  it("reads events from the live loopback API", async () => {
    const baseUrl = await serve((req, res) => {
      if (req.url?.startsWith("/events")) {
        expect(req.headers.authorization).toBe("Bearer install-token");
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            events: [
              {
                seq: 1,
                id: "evt-keep",
                type: "GoalRecorded",
                payload: { goal_id: "g1" },
                recorded_at: "2026-08-31T00:00:00+00:00",
              },
            ],
            head_seq: 1,
          }),
        );
        return;
      }
      res.writeHead(404);
      res.end();
    });

    const result = await pollEngineEvents({
      baseUrl,
      token: "install-token",
    });
    expect(result).toEqual({
      events: [
        {
          seq: 1,
          id: "evt-keep",
          type: "GoalRecorded",
          payload: { goal_id: "g1" },
          recorded_at: "2026-08-31T00:00:00+00:00",
        },
      ],
      headSeq: 1,
    });
  });
});
