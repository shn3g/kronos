// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { streamStatusMessage } from "./streamStatus";

describe("streamStatusMessage", () => {
  it("announces streaming, tool, done, and error phases in plain text", () => {
    expect(streamStatusMessage("streaming")).toBe("Streaming reply.");
    expect(streamStatusMessage("tool", "Read file")).toBe("Read file · running.");
    expect(streamStatusMessage("done")).toBe("Turn finished.");
    expect(streamStatusMessage("error")).toBe("Message failed.");
    expect(streamStatusMessage("idle")).toBeNull();
  });
});
