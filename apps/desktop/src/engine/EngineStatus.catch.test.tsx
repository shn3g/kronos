import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EngineStatus } from "./EngineStatus";
import type { EngineClient } from "./client";

describe("EngineStatus rejection handling", () => {
  it("treats a rejecting getState as unavailable", async () => {
    const client: EngineClient = {
      getState: async () => {
        throw new Error("engine probe failed");
      },
    };

    render(<EngineStatus client={client} />);

    expect(await screen.findByRole("status")).toHaveTextContent("Engine unavailable");
    expect(screen.queryByText("Engine ready")).not.toBeInTheDocument();
  });
});
