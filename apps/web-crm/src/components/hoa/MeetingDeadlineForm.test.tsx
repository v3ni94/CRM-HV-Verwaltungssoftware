import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeetingDeadlineForm } from "./MeetingDeadlineForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const M = "0192abcd-0000-7000-8000-000000000030";

describe("MeetingDeadlineForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requires a source when a deadline is set", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<MeetingDeadlineForm meetingId={M} deadline="2026-11-30" source={null} />);
    await userEvent.click(screen.getByRole("button", { name: "Frist speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte die Quelle der Frist angeben.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends deadline and source via PATCH", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: M }));
    renderIntl(<MeetingDeadlineForm meetingId={M} deadline={null} source={null} />);
    await userEvent.type(screen.getByTestId("resolution-deadline-at"), "2026-11-30");
    await userEvent.type(screen.getByTestId("resolution-deadline-source"), "Beschluss TOP 3");
    await userEvent.click(screen.getByRole("button", { name: "Frist speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(`/hoa/meetings/${M}`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      resolution_deadline_at: "2026-11-30",
      resolution_deadline_source: "Beschluss TOP 3",
    });
    expect(await screen.findByText("Frist gespeichert.")).toBeInTheDocument();
  });
});
