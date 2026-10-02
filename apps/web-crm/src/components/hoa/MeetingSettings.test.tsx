import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeetingSettings } from "./MeetingSettings";

describe("MeetingSettings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("saves the settings via PUT /hoa/meeting-settings", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MeetingSettings weeks={3} virtualEnabled={false} />);
    fireEvent.change(screen.getByTestId("invitation-weeks"), { target: { value: "4" } });
    await userEvent.click(screen.getByTestId("virtual-enabled"));
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/meeting-settings");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      invitation_weeks: 4,
      virtual_meetings_enabled: true,
      virtual_basis_term_lock_enabled: false,
      virtual_basis_transition_date: null,
    });
  });

  it("rejects weeks outside 1 to 12 without calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MeetingSettings weeks={3} virtualEnabled={false} />);
    fireEvent.change(screen.getByTestId("invitation-weeks"), { target: { value: "13" } });
    await act(async () => {
      fireEvent.submit(screen.getByTestId("meeting-settings"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the API error (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<MeetingSettings weeks={3} virtualEnabled />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
