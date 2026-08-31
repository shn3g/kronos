import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EngineStatus } from "./EngineStatus";
import type { EngineClient, EngineConnectionState } from "./client";

function clientOf(state: EngineConnectionState): EngineClient {
  return {
    getState: async () => state,
  };
}

describe("EngineStatus", () => {
  it("announces engine unavailable", async () => {
    render(<EngineStatus client={clientOf({ status: "unavailable" })} />);

    expect(await screen.findByRole("status")).toHaveTextContent("Engine unavailable");
  });

  it("announces engine starting", async () => {
    render(<EngineStatus client={clientOf({ status: "starting" })} />);

    expect(await screen.findByRole("status")).toHaveTextContent("Engine starting");
  });

  it("announces engine ready with the reported version", async () => {
    render(
      <EngineStatus client={clientOf({ status: "ready", version: "2.4.1" })} />,
    );

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Engine ready");
    expect(status).toHaveTextContent("2.4.1");
  });

  it("announces incompatible engine version with both versions", async () => {
    render(
      <EngineStatus
        client={clientOf({
          status: "incompatible",
          clientVersion: "0.1.0",
          engineVersion: "9.9.9",
        })}
      />,
    );

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Incompatible engine version");
    expect(status).toHaveTextContent("0.1.0");
    expect(status).toHaveTextContent("9.9.9");
  });
});
