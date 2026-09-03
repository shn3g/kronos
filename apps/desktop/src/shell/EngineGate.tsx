// SPDX-License-Identifier: AGPL-3.0-or-later

interface EngineGateProps {
  starting: boolean;
}

export function EngineGate({ starting }: EngineGateProps) {
  if (starting) {
    return (
      <section className="gate">
        <h1 className="gate__title">Starting Kronos</h1>
        <p className="gate__body">This usually takes a few seconds.</p>
      </section>
    );
  }
  return (
    <section className="gate">
      <h1 className="gate__title">Kronos stopped unexpectedly</h1>
      <p className="gate__body">
        Kronos is restarting the local service. If this message stays up, quit and reopen the app,
        or check Health for details.
      </p>
    </section>
  );
}

export function CheckingModelGate({ label }: { label?: string }) {
  return (
    <section className="gate">
      <h1 className="gate__title">{label ?? "Checking the model connection"}</h1>
      <p className="gate__body">
        {label
          ? "Looking up local embedding install status."
          : "Looking up the assigned model."}
      </p>
    </section>
  );
}
