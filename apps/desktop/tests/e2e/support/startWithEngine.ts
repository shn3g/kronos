// SPDX-License-Identifier: AGPL-3.0-or-later

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { E2E_AUTH_TOKEN, E2E_ENGINE_PORT, E2E_MOCK_PORT, startMockOpenAiServer } from "./mockOpenAi.ts";

export type Killable = { kill: (signal?: NodeJS.Signals) => boolean };
export type Closable = { close: () => unknown };

export type BootWithEngineDeps = {
  startMock: () => Promise<Closable>;
  spawnEngine: () => Killable;
  spawnVite: () => Killable;
  waitForEngine: (engine: Killable) => Promise<void>;
  waitForVite: () => Promise<void>;
};

export function stopWithEngineStack(parts: {
  vite?: Killable | null;
  engine?: Killable | null;
  mock?: Closable | null;
}): void {
  parts.vite?.kill("SIGTERM");
  parts.engine?.kill("SIGTERM");
  void parts.mock?.close();
}

export async function bootWithEngine(
  deps: BootWithEngineDeps,
): Promise<{ stop: () => void; engine: Killable; vite: Killable }> {
  const mock = await deps.startMock();
  let engine: Killable | undefined;
  let vite: Killable | undefined;
  const stop = () => stopWithEngineStack({ vite, engine, mock });
  try {
    engine = deps.spawnEngine();
    await deps.waitForEngine(engine);
    vite = deps.spawnVite();
    await deps.waitForVite();
    return { stop, engine, vite };
  } catch (error) {
    stop();
    throw error;
  }
}

const supportDir = dirname(fileURLToPath(import.meta.url));
const desktopRoot = join(supportDir, "../../..");
const repoRoot = join(desktopRoot, "../..");
const engineRoot = join(repoRoot, "engine");
const PATH_WITH_BINS = ["/usr/bin", "/usr/local/bin", "/bin", process.env.PATH]
  .filter((item): item is string => Boolean(item))
  .join(":");

function resolveBin(name: string, fallbacks: string[]): string {
  const fromEnv = process.env[`KRONOS_E2E_${name.toUpperCase()}`];
  if (fromEnv && existsSync(fromEnv)) {
    return fromEnv;
  }
  for (const dir of PATH_WITH_BINS.split(":")) {
    const candidate = join(dir, name);
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  for (const candidate of fallbacks) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error(`cannot find ${name} (PATH=${PATH_WITH_BINS})`);
}

async function main(): Promise<void> {
  const home = mkdtempSync(join(tmpdir(), "kronos-e2e-"));
  for (const name of ["data", "config", "cache", "logs"]) {
    mkdirSync(join(home, name), { recursive: true });
  }
  const modelsRoot = join(home, "cache", "models", "minilm-l6-v2");
  mkdirSync(modelsRoot, { recursive: true });
  writeFileSync(join(modelsRoot, "all-MiniLM-L6-v2.onnx"), "");
  writeFileSync(join(modelsRoot, "tokenizer.json"), "{}");
  writeFileSync(join(home, "cache", "models", ".active-key"), "minilm-l6-v2");
  if (!existsSync(engineRoot)) {
    throw new Error(`engine root missing: ${engineRoot}`);
  }
  const python = resolveBin("python3", ["/usr/bin/python3"]);
  const pnpm = resolveBin("pnpm", []);
  const sharedPath = { PATH: PATH_WITH_BINS };
  const engineEnv = {
    ...process.env,
    ...sharedPath,
    KRONOS_DATA_HOME: join(home, "data"),
    KRONOS_CONFIG_HOME: join(home, "config"),
    KRONOS_CACHE_HOME: join(home, "cache"),
    KRONOS_LOG_HOME: join(home, "logs"),
    KRONOS_AUTH_TOKEN: E2E_AUTH_TOKEN,
    KRONOS_BIND_HOST: "127.0.0.1",
    KRONOS_BIND_PORT: String(E2E_ENGINE_PORT),
    PYTHONUNBUFFERED: "1",
  };
  const { stop, engine, vite } = await bootWithEngine({
    startMock: () => startMockOpenAiServer(E2E_MOCK_PORT),
    spawnEngine: () => {
      const child = spawn(python, ["-m", "kronos_engine"], {
        cwd: engineRoot,
        env: engineEnv,
        stdio: ["ignore", "pipe", "pipe"],
      });
      child.on("error", (error) => {
        console.error(error);
      });
      return child;
    },
    spawnVite: () => {
      const child = spawn(pnpm, ["dev", "--host", "127.0.0.1", "--port", "1420", "--strictPort"], {
        cwd: desktopRoot,
        env: {
          ...process.env,
          ...sharedPath,
          KRONOS_ENGINE_URL: `http://127.0.0.1:${E2E_ENGINE_PORT}`,
          KRONOS_AUTH_TOKEN: E2E_AUTH_TOKEN,
          KRONOS_CONFIG_HOME: join(home, "config"),
        },
        stdio: "inherit",
      });
      child.on("error", (error) => {
        console.error(error);
      });
      return child;
    },
    waitForEngine: (child) => waitForReady(child as ChildProcess),
    waitForVite: () => waitForHttp("http://127.0.0.1:1420/", 120_000),
  });
  const engineProc = engine as ChildProcess;
  const viteProc = vite as ChildProcess;
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
  engineProc.on("exit", (code) => {
    if (code && code !== 0) {
      console.error(`kronos_engine exited ${code}`);
      stop();
      process.exit(code);
    }
  });
  viteProc.on("exit", (code) => {
    if (code && code !== 0) {
      console.error(`vite exited ${code}`);
      stop();
      process.exit(code);
    }
  });
}

function waitForReady(child: ChildProcess): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error("KRONOS_READY was not printed"));
    }, 30_000);
    let buf = "";
    const onData = (chunk: Buffer) => {
      buf += chunk.toString("utf8");
      if (buf.includes("KRONOS_READY ")) {
        clearTimeout(timeout);
        child.stdout?.off("data", onData);
        child.stderr?.off("data", onData);
        resolve();
      }
    };
    child.stdout?.on("data", onData);
    child.stderr?.on("data", onData);
    child.once("exit", (code) => {
      clearTimeout(timeout);
      reject(new Error(`engine exited ${code}: ${buf}`));
    });
  });
}

function waitForHttp(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      void fetch(url)
        .then((response) => {
          if (response.ok || response.status === 404) {
            resolve();
            return;
          }
          retry();
        })
        .catch(() => {
          retry();
        });
    };
    const retry = () => {
      if (Date.now() > deadline) {
        reject(new Error(`timed out waiting for ${url}`));
        return;
      }
      setTimeout(attempt, 250);
    };
    attempt();
  });
}

function isCliEntry(): boolean {
  const entry = process.argv[1];
  if (!entry) {
    return false;
  }
  return resolve(fileURLToPath(import.meta.url)) === resolve(entry);
}

if (isCliEntry()) {
  void main().catch((error: unknown) => {
    console.error(error);
    process.exit(1);
  });
}
