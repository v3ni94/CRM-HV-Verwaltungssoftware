import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { CallAssistantSettings } from "./CallAssistantSettings";

const m = messages.MailSettings;

describe("CallAssistantSettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves trimmed lists via PUT and shows the saved hint", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ enabled: true, sender_patterns: ["heidi"], keywords: ["anruf", "rueckruf"] }));
    renderIntl(<CallAssistantSettings initial={{ enabled: false, sender_patterns: [], keywords: [] }} />);
    await userEvent.click(screen.getByLabelText(m.callAssistantEnabled));
    await userEvent.type(screen.getByLabelText(m.callAssistantSenders), " heidi , ,");
    await userEvent.type(screen.getByLabelText(new RegExp(m.callAssistantKeywords.replace(/[()]/g, "\\$&"))), "anruf, rueckruf");
    await userEvent.click(screen.getByRole("button", { name: m.save }));
    expect(await screen.findByText(m.saved)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/mail/call-assistant");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ enabled: true, sender_patterns: ["heidi"], keywords: ["anruf", "rueckruf"] });
  });

  it("shows the API error and no saved hint", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung" }, 403));
    renderIntl(<CallAssistantSettings initial={{ enabled: true, sender_patterns: ["a"], keywords: [] }} />);
    await userEvent.click(screen.getByRole("button", { name: m.save }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(m.saved)).toBeNull();
  });
});
