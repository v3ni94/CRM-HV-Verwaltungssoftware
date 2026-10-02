import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { FinApiSettingsCard, type FinApiConfig } from "./FinApiSettingsCard";

const initial: FinApiConfig = { configured: false, base_url: null, mandator_id: null, sandbox: null, auto_fetch_enabled: false };

describe("FinApiSettingsCard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps save disabled until client id and secret are entered, then PUTs and clears the secrets", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...initial, configured: true, base_url: "https://sandbox.finapi.io", sandbox: true }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<FinApiSettingsCard initial={initial} />);
    const save = screen.getByRole("button", { name: "Speichern" });
    expect(save).toBeDisabled();
    const boxes = screen.getAllByRole("textbox");
    await userEvent.type(boxes[2]!, "cid");
    await userEvent.type(document.querySelector('input[type="password"]') as HTMLInputElement, "secret");
    expect(save).toBeEnabled();
    await act(async () => {
      await userEvent.click(save);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/banking/finapi/config");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body).toMatchObject({ client_id: "cid", client_secret: "secret", base_url: null, mandator_id: null, sandbox: true, auto_fetch_enabled: false });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).toHaveValue("");
    expect(save).toBeDisabled();
  });

  it("shows the error on 403 and keeps the entered values", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<FinApiSettingsCard initial={initial} />);
    await userEvent.type(screen.getAllByRole("textbox")[2]!, "cid");
    await userEvent.type(document.querySelector('input[type="password"]') as HTMLInputElement, "secret");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Gespeichert.")).toBeNull();
  });
});
