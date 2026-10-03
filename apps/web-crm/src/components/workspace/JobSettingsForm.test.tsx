import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { JobSettingsForm } from "./JobSettingsForm";

const m = messages.Deadlines.settings;
const INITIAL = { digest_mail_enabled: false, deadline_lead_days: 14, deadline_lead_days_default: 14 };

describe("JobSettingsForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the switches as numbers and booleans and shows the saved state", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ ...INITIAL, digest_mail_enabled: true, deadline_lead_days: 30 }));
    renderIntl(<JobSettingsForm initial={INITIAL} />);
    expect(screen.getByTestId("digest-mail")).not.toBeChecked();
    const lead = screen.getByTestId("lead-days");
    await userEvent.clear(lead);
    await userEvent.type(lead, "30");
    await userEvent.click(screen.getByTestId("digest-mail"));
    await userEvent.click(screen.getByRole("button", { name: m.save }));
    expect(await screen.findByText(m.saved)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/workspace/job-settings");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ digest_mail_enabled: true, deadline_lead_days: 30 });
  });

  it("shows the server message on failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung" }, 403));
    renderIntl(<JobSettingsForm initial={INITIAL} />);
    await userEvent.click(screen.getByRole("button", { name: m.save }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(m.saved)).toBeNull();
  });
});
