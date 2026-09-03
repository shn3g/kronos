// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import type { EngineClient } from "./client";
import { EngineConnectionProvider } from "./EngineConnectionProvider";

export function renderWithEngineConnection(
  ui: ReactElement,
  engineClient: EngineClient,
  options?: Omit<RenderOptions, "wrapper">,
): RenderResult {
  return render(ui, {
    ...options,
    wrapper: ({ children }) => (
      <EngineConnectionProvider engineClient={engineClient}>{children}</EngineConnectionProvider>
    ),
  });
}
