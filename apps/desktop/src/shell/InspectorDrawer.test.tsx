import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
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
    expect(screen.getByLabelText(/^removed\./i)).toHaveTextContent("-old");
    expect(screen.getByLabelText(/^added\./i)).toHaveTextContent("+new");
  });

  it("reverts a chat write from the Changes list when a handler is provided", async () => {
    const user = userEvent.setup();
    const onRevert = vi.fn();
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
        onRevert={onRevert}
      />,
    );

    await user.click(screen.getByRole("button", { name: /revert src\/app\.tsx/i }));
    expect(onRevert).toHaveBeenCalledWith("src/App.tsx");
  });

  it("hides Revert and Commit when those handlers are omitted", () => {
    render(
      <InspectorDrawer
        tab="changes"
        onTab={() => undefined}
        changes={[{ path: "src/App.tsx", summary: "Modified src/App.tsx" }]}
        goals={[]}
        checks={[]}
      />,
    );

    expect(screen.queryByRole("button", { name: /revert src\/app\.tsx/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^commit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /commit message/i })).not.toBeInTheDocument();
  });

  it("opens a change in Files from the Changes list", async () => {
    const user = userEvent.setup();
    const onOpenPath = vi.fn();
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
        onOpenPath={onOpenPath}
      />,
    );

    await user.click(screen.getByRole("button", { name: /open src\/app\.tsx/i }));
    expect(onOpenPath).toHaveBeenCalledWith("src/App.tsx");
    expect(screen.queryByText(/-old/)).not.toBeInTheDocument();
  });

  it("hides Open when no file opener is provided", () => {
    render(
      <InspectorDrawer
        tab="changes"
        onTab={() => undefined}
        changes={[{ path: "src/App.tsx", summary: "Modified src/App.tsx" }]}
        goals={[]}
        checks={[]}
      />,
    );

    expect(screen.queryByRole("button", { name: /open src\/app\.tsx/i })).not.toBeInTheDocument();
  });

  it("commits listed files from a local message", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    render(
      <InspectorDrawer
        tab="changes"
        onTab={() => undefined}
        changes={[
          {
            path: "src/App.tsx",
            summary: "Modified src/App.tsx",
            patch: "--- a/src/App.tsx\n+++ b/src/App.tsx\n-old\n+new\n",
          },
        ]}
        goals={[]}
        checks={[]}
        onCommit={onCommit}
      />,
    );

    const commit = screen.getByRole("button", { name: /^commit$/i });
    expect(commit).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /commit message/i }), "Fix App");
    expect(commit).toBeEnabled();
    await user.click(commit);
    expect(onCommit).toHaveBeenCalledWith("Fix App", ["src/App.tsx"]);
  });

  it("hides non-chat edits until All is chosen", async () => {
    const user = userEvent.setup();
    render(
      <InspectorDrawer
        tab="changes"
        onTab={() => undefined}
        changes={[
          {
            path: "src/App.tsx",
            summary: "Modified src/App.tsx",
            patch: "+agent\n",
            fromChat: true,
          },
          {
            path: "notes.md",
            summary: "Modified notes.md",
            patch: "+local\n",
            fromChat: false,
          },
        ]}
        goals={[]}
        checks={[]}
      />,
    );

    expect(screen.getByText("src/App.tsx")).toBeInTheDocument();
    expect(screen.queryByText("notes.md")).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /^all$/i }));
    expect(screen.getByText("notes.md")).toBeInTheDocument();
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
