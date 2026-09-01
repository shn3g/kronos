// SPDX-License-Identifier: AGPL-3.0-or-later

import type { HealthCheck } from "./checks";

interface HealthListProps {
  checks: HealthCheck[];
}

export function HealthList({ checks }: HealthListProps) {
  return (
    <ul className="health-list">
      {checks.map((item) => (
        <li key={item.id} className="health-list__item" data-ok={item.ok ? "true" : "false"}>
          <span className="health-list__mark" aria-hidden="true">
            {item.ok ? "✓" : "!"}
          </span>
          <span>
            <strong>
              {item.label}
              <span className="health-list__state">{item.ok ? "Ready" : "Needs attention"}</span>
            </strong>
            <span className="health-list__detail">{item.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
