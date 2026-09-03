// SPDX-License-Identifier: AGPL-3.0-or-later

import type { ReactNode } from "react";

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
}

export function Field({ id, label, hint, error, children }: FieldProps) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div className="field__control">
        {children}
        {hint ? <p className="field__hint">{hint}</p> : null}
        {error ? (
          <p className="field__error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
