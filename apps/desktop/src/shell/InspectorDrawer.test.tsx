import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { InspectorDrawer, type InspectorTab } from "./InspectorDrawer";

function Harness() {
  const [tab, setTab] = useState<InspectorTab>("changes");
  return (
    <InspectorDrawer
      tab={tab}
      onTab={setTab}
      changes={[{ path: "src/App.tsx", summary: "guard staff before calendar" }]}
      goals={[{ id: "goal_1", title: "Fix onboarding", state: "queued" }]}
      checks={[]}
    />
  );
}

describe("InspectorDrawer", () => {
  it("expands a change to show the unified diff", async () => {
    const user = userEvent.setup();
    render(
      <InspectorDrawer
        tab="changes"
        onTab={() => undefined}
        changes={[
          {
            path: "src/App.tsx",
            summary: "Wrote src/App.tsx",
            patch: "--- a/src/App.tsx\n+++ b/src/App.tsx\n-old\n+new\n",
          },
        ]}
        goals={[]}
        checks={[]}
      />,
    );
    expect(screen.queryByText(/-old/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /src\/app\.tsx/i }));
    expect(screen.getByText(/-old/)).toBeInTheDocument();
    expect(screen.getByText(/\+new/)).toBeInTheDocument();
  });

  it("lists workspace diffs and goal titles with text status", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByText("src/App.tsx")).toBeInTheDocument();
    expect(screen.getByText(/guard staff/i)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /goals/i }));
    expect(screen.getByText("Fix onboarding")).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();
  });
});
