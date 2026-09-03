// SPDX-License-Identifier: AGPL-3.0-or-later

import type { ReactNode } from "react";

interface FormSectionProps {
  title: string;
  lead?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function FormSection({ title, lead, actions, children }: FormSectionProps) {
  return (
    <section className="form-section">
      <header className="form-section__header">
        <div>
          <h3 className="form-section__title">{title}</h3>
          {lead ? <p className="form-section__lead">{lead}</p> : null}
        </div>
        {actions ? <div className="form-section__actions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}
