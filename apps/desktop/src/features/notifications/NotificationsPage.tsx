// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionNotificationsClient,
  type AlertView,
  type NotificationsPageClients,
} from "./client";

export type { NotificationsPageClients } from "./client";

interface NotificationsPageProps {
  engineClient: EngineClient;
  notificationsClient?: NotificationsPageClients;
}

const productionNotifications = createProductionNotificationsClient();

export function NotificationsPage({
  engineClient,
  notificationsClient,
}: NotificationsPageProps) {
  const client = notificationsClient ?? productionNotifications;
  const [ready, setReady] = useState(false);
  const [items, setItems] = useState<AlertView[]>([]);

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engineClient.getState().then((state) => {
        if (!cancelled) {
          setReady(state.status === "ready");
        }
      });
    };
    apply();
    const interval = window.setInterval(apply, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [engineClient]);

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
        <p className="page-body">
          Connect a compatible engine to inspect alerts. Dependency failures pause here with
          evidence.
        </p>
      </section>
    );
  }

  return (
    <section className="notifications-page">
      <p className="page-kicker">Notifications</p>
      <h1 className="page-title">Notifications</h1>
      <p className="page-body">Paused work and degraded indexes appear as alerts without secrets.</p>
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
