// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import { useEngineConnection } from "../../engine/EngineConnectionProvider";
import {
  createProductionNotificationsClient,
  type AlertView,
  type NotificationsPageClients,
} from "./client";

export type { NotificationsPageClients } from "./client";

interface NotificationsPageProps {
  notificationsClient?: NotificationsPageClients;
}

const productionNotifications = createProductionNotificationsClient();

export function NotificationsPage({
  notificationsClient,
}: NotificationsPageProps) {
  const client = notificationsClient ?? productionNotifications;
  const { engineReady: ready } = useEngineConnection();
  const [items, setItems] = useState<AlertView[]>([]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    let cancelled = false;
    void client.list().then((next) => {
      if (!cancelled) {
        setItems(next);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="notifications-page">
        <p className="page-kicker">Notifications</p>
        <h1 className="page-title">Notifications</h1>
        <p className="page-body">Waiting for the engine.</p>
      </section>
    );
  }

  return (
    <section className="notifications-page">
      <p className="page-kicker">Notifications</p>
      <h1 className="page-title">Notifications</h1>
      <p className="page-body">Paused work and degraded indexes appear here without secrets.</p>
      {items.length === 0 ? (
        <p className="workspaces__empty">No alerts.</p>
      ) : (
        <ul className="workspace-list">
          {items.map((item) => (
            <li key={item.id} className="workspace-card">
              <p className="workspace-card__name">{item.title}</p>
              <p className="workspace-card__meta">{item.detail}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
