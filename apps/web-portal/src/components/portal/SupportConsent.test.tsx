import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SupportConsent } from "./SupportConsent";

describe("SupportConsent", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("grants consent for the selected hours via POST /portal/support-consent", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ active: true, expires_at: "2026-10-03T10:00:00Z" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<SupportConsent initial={{ active: false, expires_at: null }} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "4");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/portal/support-consent");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ hours: 4 });
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("revokes an active consent via DELETE and shows the grant form again", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<SupportConsent initial={{ active: true, expires_at: "2026-10-03T10:00:00Z" }} />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("DELETE");
    expect(await screen.findByRole("combobox")).toBeInTheDocument();
  });

  it("shows an error when granting is refused (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<SupportConsent initial={{ active: false, expires_at: null }} />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
