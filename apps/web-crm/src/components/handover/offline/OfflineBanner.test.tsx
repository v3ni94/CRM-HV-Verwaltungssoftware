import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { OfflineBanner } from "./OfflineBanner";
import type { HandoverOffline } from "./useHandoverOffline";

function offline(overrides: Partial<HandoverOffline>): HandoverOffline {
  return {
    enabled: true,
    online: false,
    pending: [],
    lost: 0,
    view: {} as HandoverOffline["view"],
    send: vi.fn(),
    reload: vi.fn(),
    setServer: vi.fn(),
    sync: vi.fn(),
    syncState: "idle",
    conflict: null,
    resolveConflict: vi.fn(),
    failure: null,
    discardAll: vi.fn(),
    log: [],
    ...overrides,
  };
}

const item = (id: string) => ({ id, protocolId: "p", seq: 1, capturedAt: "2026-09-28T16:45:12+02:00", op: { kind: "create_item" as const, section: "rooms" as const, tempId: id, body: {} } });

describe("OfflineBanner", () => {
  it("renders nothing while the switch is off", () => {
    renderIntl(<OfflineBanner offline={offline({ enabled: false, online: false })} />);
    expect(screen.queryByTestId("offline-banner")).toBeNull();
  });

  it("shows the connection state and the number of waiting changes", () => {
    renderIntl(<OfflineBanner offline={offline({ pending: [item("a"), item("b")] })} />);
    expect(screen.getByTestId("offline-banner")).toHaveTextContent("Keine Verbindung. Offline Erfassung aktiv.");
    expect(screen.getByTestId("offline-pending")).toHaveTextContent("2 Änderungen warten auf den Abgleich.");
    expect(screen.getByTestId("offline-discard")).toBeInTheDocument();
    expect(screen.queryByTestId("offline-sync")).toBeNull();
  });

  it("offers the sync once online and reports discarded records after a reload", () => {
    const sync = vi.fn();
    renderIntl(<OfflineBanner offline={offline({ online: true, pending: [item("a")], lost: 1, sync })} />);
    screen.getByTestId("offline-sync").click();
    expect(sync).toHaveBeenCalled();
    expect(screen.getByTestId("offline-lost")).toHaveTextContent("1 lokaler Entwurf war nach dem Neuladen nicht mehr lesbar");
  });
});
