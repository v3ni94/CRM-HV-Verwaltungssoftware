import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverOfflineSwitch } from "./HandoverOfflineSwitch";

describe("HandoverOfflineSwitch", () => {
  afterEach(() => vi.restoreAllMocks());

  it("patches handover_offline_enabled and shows the state", async () => {
    const bodies: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      bodies.push(String(init?.body));
      return jsonResponse({ handover_offline_enabled: JSON.parse(String(init?.body)).handover_offline_enabled });
    });
    renderIntl(<HandoverOfflineSwitch initial={false} canUpdate />);
    expect(screen.getByTestId("handover-offline-switch-status")).toHaveTextContent("Aus");
    await userEvent.click(screen.getByLabelText("Offline Erfassung aktivieren"));
    await waitFor(() => expect(screen.getByTestId("handover-offline-switch-status")).toHaveTextContent("Aktiv"));
    expect(bodies).toEqual([JSON.stringify({ handover_offline_enabled: true })]);
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
  });

  it("is read only without the right", () => {
    renderIntl(<HandoverOfflineSwitch initial={false} canUpdate={false} />);
    expect(screen.getByLabelText("Offline Erfassung aktivieren")).toBeDisabled();
  });
});
