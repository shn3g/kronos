import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EngineStatus } from "./EngineStatus";

describe("EngineStatus", () => {
  it("announces engine unavailable", () => {
    render(<EngineStatus state={{ status: "unavailable" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("Engine unavailable");
  });

  it("announces engine starting", () => {
    render(<EngineStatus state={{ status: "starting" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("Engine starting");
  });

  it("announces engine ready with desktop and engine versions", () => {
    render(<EngineStatus state={{ status: "ready", version: "2.4.1" }} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Engine ready");
    expect(status).toHaveTextContent("Desktop 0.2.0");
    expect(status).toHaveTextContent("Engine 2.4.1");
  });

  it("announces incompatible engine version with both versions", () => {
    render(
      <EngineStatus
        state={{
          status: "incompatible",
          clientVersion: "0.2.0",
          engineVersion: "9.9.9",
        }}
      />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Incompatible engine version");
    expect(status).toHaveTextContent("0.2.0");
    expect(status).toHaveTextContent("9.9.9");
    expect(status).toHaveTextContent("on PATH");
  });
});
