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

describe("SlaSettings rules approval (M19-01)", () => {
  afterEach(() => vi.restoreAllMocks());

  const draft = {
    id: "r1",
    name: "Hoch",
    priority: "high" as const,
    response_minutes: 60,
    resolution_minutes: 600,
    clock_type: "calendar" as const,
    active: true,
    channels_by_level: null,
    category: null,
    approval_status: "draft" as const,
    approved_at: null,
    approved_by: null,
  };

  it("marks a draft, approves it through the dialog only after confirmation and omits approval fields from PATCH", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/sla/rules/r1/approve") && method === "POST") {
        expect(JSON.parse(String(init?.body))).toEqual({ confirm: true, note: "GF" });
        return jsonResponse({ ...draft, approval_status: "approved", approved_at: "2026-09-27T10:00:00Z", approved_by: "u1" }, 200);
      }
      if (url.endsWith("/api/bff/sla/rules/r1") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        expect(body.approval_status).toBeUndefined();
        expect(body.approved_at).toBeUndefined();
        return jsonResponse({ ...draft, active: false }, 200);
      }
      if (url.endsWith("/api/bff/sla/rules/r1/steps")) return jsonResponse([], 200);
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<SlaSettings {...baseProps} rules={[draft]} canApprove whatsappConfig={EMPTY_WHATSAPP_CONFIG} />);
    expect(screen.getByText("Entwurf, nicht wirksam")).toBeInTheDocument();
    expect(screen.getByText("alle Kategorien")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    const submit = screen.getByRole("button", { name: "Freigabe bestätigen" });
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Ich habe die Werte geprüft und gebe sie als Geschäftsführung frei."));
    await userEvent.type(screen.getByLabelText("Vermerk (optional)"), "GF");
    await userEvent.click(submit);
    await waitFor(() => expect(screen.getByText("Regel freigegeben.")).toBeInTheDocument());
    expect(screen.getByText(/freigegeben am/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Freigabe zurücknehmen" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Deaktivieren" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
  });

  it("shows no approval button without the management right", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([], 200));
    renderIntl(<SlaSettings {...baseProps} rules={[draft]} whatsappConfig={EMPTY_WHATSAPP_CONFIG} />);
    expect(screen.getByText("Entwurf, nicht wirksam")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Freigeben" })).toBeNull();
  });
});

describe("SlaSettings alerts acknowledgement (GAI-301)", () => {
  const alert = {
    id: "al-1",
    level: 1,
    sent_at: "2026-10-01T08:00:00Z",
    sent_to: "+49 0000",
    channel: "sms",
    delivered_at: null,
    delivery_error: null,
    acknowledged_by: null,
    acknowledged_at: null,
  };

  it("shows Quittieren with sla:update", async () => {
    renderIntl(<SlaSettings {...baseProps} alerts={[alert] as never} whatsappConfig={EMPTY_WHATSAPP_CONFIG} />);
    await userEvent.setup().click(screen.getByRole("tab", { name: "Alarme" }));
    expect(screen.getByRole("button", { name: "Quittieren" })).toBeInTheDocument();
  });

  it("hides Quittieren without sla:update", async () => {
    renderIntl(
      <SlaSettings {...baseProps} canManage={false} alerts={[alert] as never} whatsappConfig={EMPTY_WHATSAPP_CONFIG} />,
    );
    await userEvent.setup().click(screen.getByRole("tab", { name: "Alarme" }));
    expect(screen.getByText("Stufe 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Quittieren" })).not.toBeInTheDocument();
  });
});
