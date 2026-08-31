/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionRepositoriesClient } from "./client";

describe("createProductionRepositoriesClient", () => {
  it("maps enrolled repositories from the engine JSON proxy", async () => {
    const client = createProductionRepositoriesClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/repositories");
      return {
        status: 200,
        body: JSON.stringify({
          repositories: [
            {
              id: "repo_alpha",
              display_name: "alpha",
              realpath: "C:/tmp/alpha",
              origin: "https://github.com/acme/alpha.git",
              status: "paused",
            },
          ],
        }),
      };
    });

    await expect(client.list()).resolves.toEqual([
      {
        id: "repo_alpha",
        displayName: "alpha",
        realpath: "C:/tmp/alpha",
        origin: "https://github.com/acme/alpha.git",
        status: "paused",
      },
    ]);
  });
});
