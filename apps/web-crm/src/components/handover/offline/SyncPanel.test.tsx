import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { SyncPanel } from "./SyncPanel";
import type { HandoverOffline } from "./useHandoverOffline";

function offline(over: Partial<HandoverOffline>): HandoverOffline {
  return {
    enabled: true,
    online: true,
    pending: [],
    lost: 0,
    view: {} as HandoverOffline["view"],
    send: vi.fn(),
    reload: vi.fn(),
    setServer: vi.fn(),
    sync: vi.fn(),
    syncState: "idle",
    conflict: null,
    resolveConflict: vi.fn().mockResolvedValue(undefined),
    failure: null,
    discardAll: vi.fn(),
    log: [],
    ...over,
  } as HandoverOffline;
}

describe("SyncPanel (GAI-615)", () => {
  it("renders nothing while the offline switch is off", () => {
    const { container } = renderIntl(<SyncPanel offline={offline({ enabled: false })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the replay log with kind and result", () => {
    renderIntl(
      <SyncPanel
        offline={offline({ log: [{ at: "2026-10-01T10:00:00Z", capturedAt: "2026-10-01T09:00:00Z", kind: "signature", result: "ok", message: "" } as never] })}
      />,
    );
    const log = screen.getByTestId("sync-log");
    expect(log).toHaveTextContent("Abgleichsprotokoll (1)");
    expect(log).toHaveTextContent("Unterschrift");
    expect(log).toHaveTextContent("übertragen");
  });

  it("lets the person decide a conflict, nothing is decided automatically", async () => {
    const resolveConflict = vi.fn().mockResolvedValue(undefined);
    const conflict = {
      message: "Serverstand ist neuer",
      server: { name: "Server", id: "x" },
      item: { capturedAt: "2026-10-01T09:00:00Z", op: { kind: "patch_item", body: { name: "Mein Stand" } } },
    } as never;
    renderIntl(<SyncPanel offline={offline({ conflict, resolveConflict })} />);
    expect(await screen.findByText("Server")).toBeInTheDocument();
    expect(screen.getByText("Mein Stand")).toBeInTheDocument();
    expect(resolveConflict).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("conflict-keep-mine"));
    expect(resolveConflict).toHaveBeenCalledWith("mine");
    await userEvent.click(screen.getByTestId("conflict-keep-server"));
    expect(resolveConflict).toHaveBeenLastCalledWith("server");
  });
});
