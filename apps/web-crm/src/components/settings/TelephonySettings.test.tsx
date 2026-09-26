import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TelephonySettings } from "./TelephonySettings";

const initial = { enabled: false, provider_label: null, has_webhook_secret: false, webhook_path: "/api/v1/communication/webhooks/telephony" };

describe("TelephonySettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the secret once, never shows it and reports the stored state", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/communication/telephony/settings") && init?.method === "PUT") {
        return jsonResponse({ ...initial, enabled: true, provider_label: "Anlage", has_webhook_secret: true }, 200);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<TelephonySettings initial={initial} canManage />);
    expect(screen.getByText("/api/v1/communication/webhooks/telephony")).toBeInTheDocument();
    const secret = screen.getByLabelText(/Geheimnis/);
    expect(secret).toHaveAttribute("placeholder", "Noch kein Geheimnis hinterlegt.");
    await userEvent.type(secret, "ein-langes-geheimnis-1234");
    await userEvent.type(screen.getByLabelText(/Anbieter/), "Anlage");
    await userEvent.click(screen.getByLabelText(/Webhook aktiv/));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Einstellungen gespeichert.")).toBeInTheDocument());
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/bff/communication/telephony/settings"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ enabled: true, provider_label: "Anlage", webhook_secret: "ein-langes-geheimnis-1234" });
    expect(secret).toHaveValue("");
    expect(secret).toHaveAttribute("placeholder", "Geheimnis ist hinterlegt und wird nicht angezeigt.");
  });

  it("is read only without the permission", () => {
    renderIntl(<TelephonySettings initial={initial} canManage={false} />);
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Geheimnis/)).toBeDisabled();
  });
});
