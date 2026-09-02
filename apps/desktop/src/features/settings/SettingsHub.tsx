// SPDX-License-Identifier: AGPL-3.0-or-later

import type { EngineClient } from "../../engine/client";
import { GitHubPage } from "../connections/github/GitHubPage";
import { TelegramPage } from "../connections/telegram/TelegramPage";
import { IndexPage } from "../index/IndexPage";
import { MemoryPage } from "../memory/MemoryPage";
import { ModelsPage, type ModelsClient } from "../models/ModelsPage";
import { NotificationsPage } from "../notifications/NotificationsPage";
import { SkillsPage } from "../skills/SkillsPage";
import { UpdatesPage } from "../updates/UpdatesPage";
import { SETTINGS_SECTIONS, type SettingsSection } from "../../shell/routes";
import { SettingsPage, type SettingsPageClients } from "./SettingsPage";

interface SettingsHubProps {
  engineClient: EngineClient;
  section: SettingsSection;
  onSection: (section: SettingsSection) => void;
  modelsClient?: ModelsClient;
  settingsClient?: SettingsPageClients;
}

export function SettingsHub({
  engineClient,
  section,
  onSection,
  modelsClient,
  settingsClient,
}: SettingsHubProps) {
  return (
    <div className="settings-hub">
      <nav className="settings-hub__nav" aria-label="Settings">
        {SETTINGS_SECTIONS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-current={section === item.id ? "page" : undefined}
            onClick={() => {
              onSection(item.id);
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="settings-hub__panel">
        {section === "general" ? (
          <SettingsPage
            engineClient={engineClient}
            {...(settingsClient ? { settingsClient } : {})}
          />
        ) : null}
        {section === "models" ? (
          <ModelsPage engineClient={engineClient} {...(modelsClient ? { modelsClient } : {})} />
        ) : null}
        {section === "index" ? <IndexPage engineClient={engineClient} /> : null}
        {section === "connections" ? (
          <>
            <GitHubPage engineClient={engineClient} />
            <TelegramPage engineClient={engineClient} />
          </>
        ) : null}
        {section === "skills" ? <SkillsPage engineClient={engineClient} /> : null}
        {section === "memory" ? <MemoryPage engineClient={engineClient} /> : null}
        {section === "updates" ? <UpdatesPage engineClient={engineClient} /> : null}
        {section === "notifications" ? <NotificationsPage engineClient={engineClient} /> : null}
      </div>
    </div>
  );
}
