// SPDX-License-Identifier: AGPL-3.0-or-later

interface WorkspaceGateProps {
  onOpenWorkspace: () => void;
  onSkip: () => void;
}

export function WorkspaceGate({ onOpenWorkspace, onSkip }: WorkspaceGateProps) {
  return (
    <section className="gate">
      <p className="gate__step">Step 3 of 3 · Open a workspace (optional)</p>
      <h1 className="gate__title">Open a workspace</h1>
      <p className="gate__body">
        Enrol a git folder to index code, edit files, and run the terminal. You can skip and chat
        about Kronos first.
      </p>
      <div className="gate__actions">
        <button type="button" className="btn-primary" onClick={onOpenWorkspace}>
          Open a folder
        </button>
        <button type="button" className="btn-quiet" onClick={onSkip}>
          Skip for now
        </button>
      </div>
    </section>
  );
}
