import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { EMPTY_SMS_GATEWAY, EMPTY_WHATSAPP_CONFIG, SlaSettings } from "./SlaSettings";

const baseProps = {
  rules: [],
  onCall: [],
  currentOnCall: null,
  calendar: {
    weekdays: [0, 1, 2, 3, 4],
    opens_at: "08:00",
    closes_at: "16:30",
    timezone: "Europe/Berlin",
    holidays: [],
  },
  alerts: [],
  members: [],
  canManage: true,
  smsGateway: EMPTY_SMS_GATEWAY,
};

describe("SlaSettings WhatsApp tab", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the WhatsApp configuration and sends a test message", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/sla/whatsapp-config") && method === "PUT") {
        return jsonResponse(
          {
            enabled: true,
            phone_number_id: "1234567890",
            whatsapp_business_account_id: "999",
            access_token_set: true,
            template_names: { sla_escalation: "sla_eskalation_de" },
            template_language: "de",
            sms_fallback: true,
          },
          200,
        );
      }
      if (url.endsWith("/api/bff/sla/whatsapp-config/test") && method === "POST") {
        return jsonResponse({ ok: true, error: null }, 200);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<SlaSettings {...baseProps} whatsappConfig={EMPTY_WHATSAPP_CONFIG} />);

    await userEvent.click(screen.getByRole("tab", { name: "WhatsApp" }));
    await userEvent.click(screen.getByLabelText("Aktiv"));
    await userEvent.type(screen.getByLabelText("Telefonnummer-ID"), "1234567890");
    await userEvent.type(screen.getByLabelText("WhatsApp-Business-Account-ID"), "999");
    await userEvent.type(screen.getByLabelText("Zugriffstoken"), "geheim-wa-token");
    await userEvent.type(screen.getByLabelText("SLA-Eskalation"), "sla_eskalation_de");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    const saveCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/bff/sla/whatsapp-config"),
    );
    expect(saveCall).toBeDefined();
    const body = JSON.parse(String(saveCall?.[1]?.body));
    expect(body.enabled).toBe(true);
    expect(body.phone_number_id).toBe("1234567890");
    expect(body.access_token).toBe("geheim-wa-token");
    expect(body.template_names).toEqual({ sla_escalation: "sla_eskalation_de" });

    await userEvent.type(screen.getByLabelText("Testnummer (Mitarbeiter)"), "+491701234567");
    await userEvent.click(screen.getByRole("button", { name: "Testnachricht senden" }));
    await waitFor(() =>
      expect(screen.getByText("Testnachricht wurde von der Cloud API angenommen.")).toBeInTheDocument(),
    );
  });

  it("shows a fallback hint and the WhatsApp channel option in the escalation editor", async () => {
    renderIntl(<SlaSettings {...baseProps} whatsappConfig={EMPTY_WHATSAPP_CONFIG} />);
    await userEvent.click(screen.getByRole("tab", { name: "WhatsApp" }));
    expect(
      screen.getByLabelText("SMS als Rückfall verwenden, wenn WhatsApp fehlschlägt"),
    ).toBeInTheDocument();
  });
});
