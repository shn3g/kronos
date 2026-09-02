// SPDX-License-Identifier: AGPL-3.0-or-later

interface EngineGateProps {
  starting: boolean;
}

export function EngineGate({ starting }: EngineGateProps) {
  if (starting) {
    return (
      <section className="gate">
        <h1 className="gate__title">Starting Kronos</h1>
        <p className="gate__body">Waiting for the local engine. This usually takes a few seconds.</p>
      </section>
    );
  }
  return (
    <section className="gate">
      <h1 className="gate__title">The local engine is not running</h1>
      <p className="gate__body">
        Kronos is a desktop app that talks to a local engine on this machine. Start the app from
        the installer, or run the engine from a developer checkout, then try again.
      </p>
    </section>
  );
}

export function CheckingModelGate() {
  return (
    <section className="gate">
      <h1 className="gate__title">Checking the model connection</h1>
      <p className="gate__body">The local engine is ready. Looking up the assigned model.</p>
    </section>
  );
}
