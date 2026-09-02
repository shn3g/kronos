// SPDX-License-Identifier: AGPL-3.0-or-later

import type { EnrolledRepository } from "../workspaces/client";
import type { GoalDraft } from "./client";

interface GoalCreateWizardProps {
  draft: GoalDraft;
  repositories: EnrolledRepository[];
  onDraftChange: (draft: GoalDraft) => void;
  onSubmit: () => void;
}

export function GoalCreateWizard({
  draft,
  repositories,
  onDraftChange,
  onSubmit,
}: GoalCreateWizardProps) {
  return (
    <form
      className="wizard"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <h2 className="wizard__title">Create goal</h2>
      <label className="wizard__label" htmlFor="goal-repo">
        Repository
        <select
          id="goal-repo"
          className="wizard__input"
          value={draft.repositoryId}
          onChange={(event) => {
            onDraftChange({ ...draft, repositoryId: event.target.value });
          }}
        >
          {repositories.map((repo) => (
            <option key={repo.id} value={repo.id}>
              {repo.displayName}
            </option>
          ))}
        </select>
      </label>
      <label className="wizard__label" htmlFor="goal-title">
        Title
        <input
          id="goal-title"
          className="wizard__input"
          value={draft.title}
          onChange={(event) => {
            onDraftChange({ ...draft, title: event.target.value });
          }}
        />
      </label>
      <label className="wizard__label" htmlFor="goal-criteria">
        Success criteria
        <textarea
          id="goal-criteria"
          className="wizard__input"
          value={draft.successCriteria}
          onChange={(event) => {
            onDraftChange({ ...draft, successCriteria: event.target.value });
          }}
        />
      </label>
      <label className="wizard__label" htmlFor="goal-nongoals">
        Non-goals
        <textarea
          id="goal-nongoals"
          className="wizard__input"
          value={draft.nonGoals}
          onChange={(event) => {
            onDraftChange({ ...draft, nonGoals: event.target.value });
          }}
        />
      </label>
      <label className="wizard__label" htmlFor="goal-risk">
        Risk ceiling
        <select
          id="goal-risk"
          className="wizard__input"
          value={draft.riskCeiling}
          onChange={(event) => {
            onDraftChange({ ...draft, riskCeiling: event.target.value });
          }}
        >
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>
      </label>
      <label className="wizard__label" htmlFor="goal-budget">
        Attempt budget
        <input
          id="goal-budget"
          className="wizard__input"
          type="number"
          min={1}
          value={draft.maxAttempts}
          onChange={(event) => {
            onDraftChange({ ...draft, maxAttempts: Number(event.target.value) });
          }}
        />
      </label>
      <button type="submit" className="btn-primary">
        Create goal
      </button>
    </form>
  );
}
