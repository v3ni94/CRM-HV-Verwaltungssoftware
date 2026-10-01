import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TenantDefaultsAdmin, type NumberFormatEntry } from "./TenantDefaultsAdmin";

const row = (scope: string, over: Partial<NumberFormatEntry> = {}): NumberFormatEntry => ({
  scope,
  prefix: "",
  digits: 6,
  start: 1,
  year_based: false,
  locked: false,
  is_default: true,
  preview: ["000001", "000002", "000003"],
  ...over,
});

describe("TenantDefaultsAdmin", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("saves the default delivery channel", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ default_delivery_channel: "email" }));
    renderIntl(<TenantDefaultsAdmin initialChannel="post" initialFormats={[row("contract")]} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "email");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain("/tenant/delivery-default");
    expect(JSON.parse(String(init?.body))).toEqual({ default_delivery_channel: "email" });
  });

  it("locks the invoice circle and sends only unlocked circles", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ formats: [row("contract", { prefix: "V" }), row("invoice", { locked: true })] }));
    renderIntl(<TenantDefaultsAdmin initialChannel="post" initialFormats={[row("contract"), row("invoice", { locked: true, prefix: "MR" })]} />);
    expect(screen.getByLabelText("Präfix Rechnung")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Nummernkreise speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(String((fetchMock.mock.calls[0] as [string, RequestInit])[1].body)) as { formats: Record<string, unknown> };
    expect(Object.keys(body.formats)).toEqual(["contract"]);
  });
});
