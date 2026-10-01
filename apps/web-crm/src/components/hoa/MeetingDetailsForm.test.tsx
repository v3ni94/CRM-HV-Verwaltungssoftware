import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AgendaResultForm, MeetingDetailsForm, type MeetingDetails } from "./MeetingDetailsForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const M = "0192abcd-0000-7000-8000-000000000060";
const I = "0192abcd-0000-7000-8000-000000000061";
const data: MeetingDetails = {
  kind: "repeat",
  scheduled_at: "2026-12-10T17:00:00Z",
  ends_at: null,
  origin_meeting_id: "0192abcd-0000-7000-8000-000000000062",
  public_description: null,
  internal_description: null,
  invitation_template_id: null,
  proxy_template_id: null,
  ballot_template_id: null,
};

describe("MeetingDetailsForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the kind and sends descriptions via PATCH", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: M }));
    renderIntl(<MeetingDetailsForm meetingId={M} data={data} closed={false} />);
    expect(screen.getByTestId("meeting-kind")).toHaveTextContent("Wiederholungsversammlung");
    await userEvent.type(screen.getByTestId("meeting-public-description"), "Wiederholung");
    await userEvent.type(screen.getByTestId("meeting-internal-description"), "Intern");
    await userEvent.click(screen.getByRole("button", { name: "Angaben speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(`/hoa/meetings/${M}`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({
      public_description: "Wiederholung",
      internal_description: "Intern",
      ends_at: null,
    });
    expect(await screen.findByText("Angaben gespeichert.")).toBeInTheDocument();
  });

  it("refuses an end before the start without a request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<MeetingDetailsForm meetingId={M} data={{ ...data, ends_at: "2026-12-10T16:00:00Z" }} closed={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Angaben speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Das Ende muss nach dem Beginn liegen.");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("MeetingDetailsForm templates", () => {
  afterEach(() => vi.restoreAllMocks());

  it("selects templates from a list and sends the id", async () => {
    const T = "0192abcd-0000-7000-8000-000000000099";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: M }));
    renderIntl(<MeetingDetailsForm meetingId={M} data={data} closed={false} templates={[{ id: T, name: "Einladung WEG" }]} />);
    await userEvent.selectOptions(screen.getByTestId("meeting-invitation_template_id"), T);
    await userEvent.click(screen.getByRole("button", { name: "Angaben speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toMatchObject({ invitation_template_id: T, proxy_template_id: null });
  });
});

describe("AgendaResultForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("records a deferral", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: I, result: "deferred" }));
    renderIntl(<AgendaResultForm itemId={I} result={null} minutesText={null} closed={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Ergebnis setzen: vertagt" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(`/hoa/agenda/${I}`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ result: "deferred" });
  });

  it("offers no result buttons after the announcement", () => {
    renderIntl(<AgendaResultForm itemId={I} result="accepted" minutesText="Text" closed={false} />);
    expect(screen.getByTestId(`agenda-result-${I}`)).toHaveTextContent("angenommen");
    expect(screen.queryByRole("button", { name: /Ergebnis setzen/ })).toBeNull();
  });
});
