import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeetingDisruptions } from "./MeetingDisruptions";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const rows = [{ id: "d1", resolved: false, description: "Ton fiel aus", occurred_at: "2026-09-30T10:00:00Z", affected_contract_ids: ["a", "b"] }];

describe("MeetingDisruptions", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    refresh.mockClear();
  });

  it("lists entries and hides the form when the meeting is closed", () => {
    renderIntl(<MeetingDisruptions meetingId="m1" rows={rows} closed />);
    expect(screen.getByText(/Ton fiel aus/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("validates required fields before posting", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MeetingDisruptions meetingId="m1" rows={[]} closed={false} />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the disruption to the BFF", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MeetingDisruptions meetingId="m1" rows={[]} closed={false} />);
    await userEvent.type(screen.getAllByRole("textbox")[0]!, "Verbindung weg");
    const dt = document.querySelector('input[type="datetime-local"]') as HTMLInputElement;
    await userEvent.type(dt, "2026-09-30T10:00");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/meetings/m1/disruptions");
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body.description).toBe("Verbindung weg");
    expect(body.resolved).toBe(false);
    expect(refresh).toHaveBeenCalled();
  });
});
