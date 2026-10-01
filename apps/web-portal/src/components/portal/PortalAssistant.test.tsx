import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalAssistant } from "./PortalAssistant";
import type { AssistantAnswer, AssistantStatus } from "./types";

const NOTICE = "Automatisch erstellte Hinweise, keine Auskunft der Verwaltung.";

function statusBody(overrides: Partial<AssistantStatus> = {}): AssistantStatus {
  return {
    enabled: true,
    privacy: { feature_enabled: false, notice_status: "not_required", title: null, body: null, version: null, acknowledged: false },
    ai: { available: false, blocked_code: "privacy_feature_off", blocked_message: "Die KI-Antwort ist nicht eingeschaltet." },
    scope: { units: 1, documents: 2 },
    hourly_limit: 20,
    notice: NOTICE,
    emergency_note: "Bei Gefahr rufen Sie bitte den Notruf 112 an.",
    ...overrides,
  };
}

const SCOPE = {
  focus_unit_id: null,
  units: [{ id: "u1", number: "01", label: "WE 01" }],
  documents: [{ document_id: "d1", title: "Wirtschaftsplan" }],
  total_documents: 1,
};

function answerBody(overrides: Partial<AssistantAnswer> = {}): AssistantAnswer {
  return {
    id: "a1",
    mode: "search",
    status: "search_hits",
    answer: "Die KI-Antwort ist nicht eingeschaltet.",
    sources: [],
    hits: [{ document_id: "d1", title: "Wirtschaftsplan" }],
    ai_available: false,
    ai_blocked_code: "privacy_feature_off",
    ai_blocked_reason: "Die KI-Antwort ist nicht eingeschaltet.",
    notice: NOTICE,
    emergency_note: "Bei Gefahr rufen Sie bitte den Notruf 112 an.",
    created_at: "2026-10-01T10:00:00Z",
    ...overrides,
  };
}

type Routes = Record<string, () => Response>;

function mockApi(routes: Routes) {
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const method = (init as RequestInit | undefined)?.method ?? "GET";
    const key = `${method} ${String(input)}`;
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected request ${key}`);
    return handler();
  });
}

const STATUS = "GET /api/bff/portal/assistant/status";
const SCOPE_URL = "GET /api/bff/portal/assistant/scope";
const HISTORY = "GET /api/bff/portal/assistant/questions?limit=10";
const ASK = "POST /api/bff/portal/assistant/questions";
const ACK = "POST /api/bff/portal/assistant/privacy-ack";

describe("PortalAssistant", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("shows a hint when the tenant switch is off (403 of the API)", async () => {
    mockApi({
      [STATUS]: () =>
        jsonResponse({ code: "MHVP-PORTAL-0001", title: "Der Assistent ist nicht freigeschaltet", status: 403 }, 403),
    });
    renderIntl(<PortalAssistant />);
    expect(await screen.findByTestId("assistant-locked")).toHaveTextContent("nicht freigeschaltet");
    expect(screen.queryByRole("button", { name: "Frage stellen" })).toBeNull();
  });

  it("shows the scope size, the disclaimer and the reason why no AI answer is given", async () => {
    mockApi({ [STATUS]: () => jsonResponse(statusBody()), [SCOPE_URL]: () => jsonResponse(SCOPE), [HISTORY]: () => jsonResponse([]) });
    renderIntl(<PortalAssistant />);
    expect(await screen.findByTestId("assistant-scope")).toHaveTextContent("2 Unterlagen");
    expect(screen.getByText(NOTICE)).toBeInTheDocument();
    expect(screen.getByTestId("assistant-ai-blocked")).toHaveTextContent("nicht eingeschaltet");
    expect(screen.getByText("Noch keine Fragen gestellt.")).toBeInTheDocument();
  });

  it("states that nothing is released for an account without grants", async () => {
    mockApi({
      [STATUS]: () => jsonResponse(statusBody({ scope: { units: 0, documents: 0 } })),
      [SCOPE_URL]: () => jsonResponse({ focus_unit_id: null, units: [], documents: [], total_documents: 0 }),
      [HISTORY]: () => jsonResponse([]),
    });
    renderIntl(<PortalAssistant />);
    expect(await screen.findByTestId("assistant-scope")).toHaveTextContent("keine Unterlagen freigegeben");
  });

  it("asks a question and labels search hits as such, never as an AI answer", async () => {
    const user = userEvent.setup();
    mockApi({
      [STATUS]: () => jsonResponse(statusBody()),
      [SCOPE_URL]: () => jsonResponse(SCOPE),
      [HISTORY]: () => jsonResponse([]),
      [ASK]: () => jsonResponse(answerBody(), 201),
    });
    renderIntl(<PortalAssistant />);
    await screen.findByTestId("portal-assistant");
    await user.type(screen.getByLabelText("Ihre Frage"), "Wie hoch ist das Hausgeld?");
    await user.click(screen.getByRole("button", { name: "Frage stellen" }));
    const card = await screen.findByTestId("assistant-answer");
    expect(card).toHaveTextContent("Treffer in Ihren Unterlagen");
    expect(card).not.toHaveTextContent("KI-Antwort, automatisch erstellt");
    expect(screen.getByTestId("assistant-hits")).toHaveTextContent("Wirtschaftsplan");
    const call = vi.mocked(fetch).mock.calls.find((c) => String(c[0]).endsWith("/questions") && (c[1] as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({ question: "Wie hoch ist das Hausgeld?" });
  });

  it("marks an AI answer and lists the checked sources", async () => {
    const user = userEvent.setup();
    mockApi({
      [STATUS]: () => jsonResponse(statusBody({ ai: { available: true, blocked_code: null, blocked_message: null } })),
      [SCOPE_URL]: () => jsonResponse(SCOPE),
      [HISTORY]: () => jsonResponse([]),
      [ASK]: () =>
        jsonResponse(
          answerBody({
            mode: "ai",
            status: "answered",
            answer: "Das Hausgeld beträgt 250,00 EUR.",
            sources: [{ document_id: "d1", title: "Wirtschaftsplan", excerpt: "Das Hausgeld beträgt 250 EUR" }],
            ai_available: true,
          }),
          201,
        ),
    });
    renderIntl(<PortalAssistant />);
    await screen.findByTestId("portal-assistant");
    expect(screen.queryByTestId("assistant-ai-blocked")).toBeNull();
    await user.type(screen.getByLabelText("Ihre Frage"), "Hausgeld?");
    await user.click(screen.getByRole("button", { name: "Frage stellen" }));
    const card = await screen.findByTestId("assistant-answer");
    expect(card).toHaveTextContent("KI-Antwort, automatisch erstellt");
    expect(card).toHaveTextContent("Das Hausgeld beträgt 250,00 EUR.");
    expect(screen.getByTestId("assistant-sources")).toHaveTextContent("Wirtschaftsplan");
  });

  it("needs the acknowledgement of the released privacy notice before a question", async () => {
    const user = userEvent.setup();
    let acknowledged = false;
    const privacy = () => ({
      feature_enabled: true,
      notice_status: "released" as const,
      title: "Datenschutzhinweis zur KI-Antwort",
      body: "Testtext des Mandanten.",
      version: 3,
      acknowledged,
    });
    mockApi({
      [STATUS]: () => jsonResponse(statusBody({ privacy: privacy() })),
      [SCOPE_URL]: () => jsonResponse(SCOPE),
      [HISTORY]: () => jsonResponse([]),
      [ACK]: () => {
        acknowledged = true;
        return jsonResponse({ acknowledged: true, text_version: 3, acknowledged_at: "2026-10-01T10:00:00Z" });
      },
    });
    renderIntl(<PortalAssistant />);
    expect(await screen.findByTestId("assistant-privacy-body")).toHaveTextContent("Testtext des Mandanten.");
    expect(screen.getByRole("button", { name: "Frage stellen" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Ich habe den Hinweis zur Kenntnis genommen" }));
    await waitFor(() => expect(screen.getByTestId("assistant-acknowledged")).toBeInTheDocument());
    const call = vi.mocked(fetch).mock.calls.find((c) => String(c[0]).endsWith("/privacy-ack"));
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({ text_version: 3 });
    expect(screen.getByRole("button", { name: "Frage stellen" })).toBeEnabled();
  });

  it("tells that the privacy notice is not released yet and offers no acknowledgement", async () => {
    mockApi({
      [STATUS]: () =>
        jsonResponse(
          statusBody({ privacy: { feature_enabled: true, notice_status: "not_released", title: null, body: null, version: null, acknowledged: false } }),
        ),
      [SCOPE_URL]: () => jsonResponse(SCOPE),
      [HISTORY]: () => jsonResponse([]),
    });
    renderIntl(<PortalAssistant />);
    expect(await screen.findByText(/noch nicht freigegeben/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /zur Kenntnis genommen/ })).toBeNull();
  });

  it("validates the question length and shows API errors", async () => {
    const user = userEvent.setup();
    mockApi({
      [STATUS]: () => jsonResponse(statusBody()),
      [SCOPE_URL]: () => jsonResponse(SCOPE),
      [HISTORY]: () => jsonResponse([]),
      [ASK]: () => jsonResponse({ code: "MHVP-CORE-0006", title: "Zu viele Anfragen", detail: "Es sind höchstens 20 Fragen pro Stunde möglich.", status: 429 }, 429),
    });
    renderIntl(<PortalAssistant />);
    await screen.findByTestId("portal-assistant");
    await user.type(screen.getByLabelText("Ihre Frage"), "ab");
    await user.click(screen.getByRole("button", { name: "Frage stellen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("mindestens drei Zeichen");
    await user.type(screen.getByLabelText("Ihre Frage"), "c Hausgeld");
    await user.click(screen.getByRole("button", { name: "Frage stellen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("höchstens 20 Fragen");
  });
});
