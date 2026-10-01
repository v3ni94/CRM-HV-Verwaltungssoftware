import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeetingClose } from "./MeetingClose";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const MEETING = "0192abcd-0000-7000-8000-000000000302";
const base = {
  meetingId: MEETING,
  minutesDocumentId: null,
  closeRequestedAt: null,
  closedAt: null,
};

describe("MeetingClose", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requests the closing with the signed minutes", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => jsonResponse({ status: "closing" }));
    renderIntl(<MeetingClose {...base} status="held" />);
    expect(screen.getByText("Abschluss beantragen")).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText("Dokument-ID des unterschriebenen Protokolls"),
      "doc-1",
    );
    await userEvent.click(screen.getByText("Abschluss beantragen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      `/api/bff/hoa/meetings/${MEETING}/close`,
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      minutes_document_id: "doc-1",
    });
    expect(
      screen.getByText(/berechnet und sperrt keine Protokollfrist/),
    ).toBeInTheDocument();
  });

  it("confirms as second person and reports the four eyes conflict", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse(
        {
          title: "Konflikt",
          detail: "Vier-Augen-Prinzip: Bestätigung durch eine zweite Person.",
        },
        409,
      ),
    );
    renderIntl(
      <MeetingClose
        {...base}
        status="closing"
        minutesDocumentId="doc-1"
        closeRequestedAt="2026-06-21T08:00:00Z"
      />,
    );
    await userEvent.click(
      screen.getByText("Abschluss bestätigen (zweite Person)"),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/zweite Person/);
    expect(screen.getByText("Antrag zurückziehen")).toBeInTheDocument();
  });

  it("shows the closed state without actions and hides before the meeting", () => {
    const { unmount } = renderIntl(
      <MeetingClose
        {...base}
        status="closed"
        closedAt="2026-06-22T08:00:00Z"
      />,
    );
    expect(screen.getByText(/Protokoll abgeschlossen am/)).toBeInTheDocument();
    expect(screen.queryByText("Abschluss beantragen")).not.toBeInTheDocument();
    unmount();
    renderIntl(<MeetingClose {...base} status="planned" />);
    expect(screen.queryByTestId("meeting-close")).not.toBeInTheDocument();
  });
});
