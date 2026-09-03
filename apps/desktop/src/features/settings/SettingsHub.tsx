// SPDX-License-Identifier: AGPL-3.0-or-later

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
  section: SettingsSection;
  onSection: (section: SettingsSection) => void;
  modelsClient?: ModelsClient;
  settingsClient?: SettingsPageClients;
}

export function SettingsHub({
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
          <SettingsPage {...(settingsClient ? { settingsClient } : {})} />
        ) : null}
        {section === "models" ? (
          <ModelsPage {...(modelsClient ? { modelsClient } : {})} />
        ) : null}
        {section === "index" ? <IndexPage /> : null}
        {section === "connections" ? (
          <>
            <GitHubPage />
            <TelegramPage />
          </>
        ) : null}
        {section === "skills" ? <SkillsPage /> : null}
        {section === "memory" ? <MemoryPage /> : null}
        {section === "updates" ? <UpdatesPage /> : null}
        {section === "notifications" ? <NotificationsPage /> : null}
      </div>
    </div>
  );
}
