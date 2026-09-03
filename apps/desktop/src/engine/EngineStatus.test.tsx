import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DESKTOP_CLIENT_VERSION } from "../api/kronosClient";
import { EngineStatus } from "./EngineStatus";

describe("EngineStatus", () => {
  it("announces when Kronos stopped and is restarting", () => {
    render(<EngineStatus state={{ status: "unavailable" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("Kronos stopped");
  });

  it("announces when Kronos is starting", () => {
    render(<EngineStatus state={{ status: "starting" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("Starting Kronos");
  });

  it("announces ready with desktop and service versions", () => {
    render(<EngineStatus state={{ status: "ready", version: "2.4.1" }} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Kronos ready");
    expect(status).toHaveTextContent(`Desktop ${DESKTOP_CLIENT_VERSION}`);
    expect(status).toHaveTextContent("Service 2.4.1");
  });

  it("announces incompatible versions", () => {
    render(
      <EngineStatus
        state={{
          status: "incompatible",
          clientVersion: DESKTOP_CLIENT_VERSION,
          engineVersion: "9.9.9",
        }}
      />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Version mismatch");
    expect(status).toHaveTextContent(DESKTOP_CLIENT_VERSION);
    expect(status).toHaveTextContent("9.9.9");
  });
});
