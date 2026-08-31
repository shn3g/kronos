import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../shell/App";
import type { EngineClient, EngineConnectionState } from "../engine/client";

function clientOf(state: EngineConnectionState): EngineClient {
  return {
    getState: async () => state,
  };
}

const routes = [
  { name: "Home", heading: "Home" },
  { name: "Workspaces", heading: "Workspaces" },
  { name: "Goals", heading: "Goals" },
  { name: "Runs", heading: "Runs" },
  { name: "Skills", heading: "Skills" },
  { name: "Memory", heading: "Memory" },
  { name: "Models", heading: "Models" },
  { name: "Index", heading: "Index" },
  { name: "Connections", heading: "Connections" },
] as const;

describe("App shell", () => {
  it("shows engine unavailable by default without an injected client", async () => {
    render(<App />);

    expect(await screen.findByRole("status")).toHaveTextContent("Engine unavailable");
    expect(screen.queryByText("Engine ready")).not.toBeInTheDocument();
  });

  it("keeps engine status visible while navigating primary routes", async () => {
    const user = userEvent.setup();
    render(<App engineClient={clientOf({ status: "starting" })} />);

    for (const route of routes) {
      await user.click(screen.getByRole("link", { name: new RegExp(`^${route.name}$`) }));
      expect(await screen.findByRole("heading", { level: 1, name: route.heading })).toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent("Engine starting");
      expect(screen.queryByText("Engine ready")).not.toBeInTheDocument();
    }
  });
});
