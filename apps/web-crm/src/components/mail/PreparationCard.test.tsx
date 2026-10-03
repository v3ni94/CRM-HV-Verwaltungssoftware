import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Preparation } from "@/lib/ai";
import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { PreparationCard } from "./PreparationCard";
import type { Message } from "./MailWorkspace";

const m = messages.Mail.preparation;

const PREP: Preparation = {
  contact_id: "c1",
  unit_id: "u1",
  property_id: "p1",
  role: "owner",
  documents: [{ document_id: "d1", title: "Hausgeldabrechnung 2025", source: "dms", matched_keyword: "abrechnung", ref: "r1" }],
  draft: "Sehr geehrte Frau Muster, anbei die Unterlagen.",
  confidence: "high",
  reasons: ["Absender passt zu Kontakt"],
  status: "ready",
};

function msg(over: Record<string, unknown> = {}, preparation?: Preparation): Message {
  return { id: "m1", direction: "in", suggestion: { preparation }, ...over } as unknown as Message;
}

describe("PreparationCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing for outgoing mails", () => {
    const { container } = renderIntl(<PreparationCard message={msg({ direction: "out" })} onDraftCreated={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the empty hint and computes a preparation via POST", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(PREP));
    renderIntl(<PreparationCard message={msg()} onDraftCreated={vi.fn()} />);
    expect(screen.getByText(m.empty)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: m.compute }));
    expect(await screen.findByText("Hausgeldabrechnung 2025")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/mail/messages/m1/preparation");
    expect(fetchMock.mock.calls[0]![1]?.method).toBe("POST");
    expect(screen.getByText(`${m.role}: Eigentümer`)).toBeInTheDocument();
    expect(screen.getByText(PREP.draft!)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.recompute })).toBeInTheDocument();
  });

  it("applies the draft as reply draft, nothing is sent", async () => {
    const created = { id: "m1", direction: "in" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(created));
    const onDraftCreated = vi.fn();
    renderIntl(<PreparationCard message={msg({}, PREP)} onDraftCreated={onDraftCreated} />);
    await userEvent.click(screen.getByRole("button", { name: m.apply }));
    await screen.findByRole("button", { name: m.apply });
    expect(onDraftCreated).toHaveBeenCalledWith(created);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/mail/messages/m1/reply-draft");
    expect(JSON.parse(String(init?.body))).toEqual({ body: PREP.draft });
  });

  it("offers no apply button without draft and shows an unknown role", () => {
    renderIntl(<PreparationCard message={msg({}, { ...PREP, draft: null, role: null, status: "skipped" })} onDraftCreated={vi.fn()} />);
    expect(screen.queryByRole("button", { name: m.apply })).toBeNull();
    expect(screen.getByText(`${m.role}: ${m.roleUnknown}`)).toBeInTheDocument();
    expect(screen.getByText(m.status.skipped)).toBeInTheDocument();
  });

  it("sends a correction only with a note and recomputes afterwards", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(PREP));
    renderIntl(<PreparationCard message={msg({}, PREP)} onDraftCreated={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: m.correct }));
    const save = screen.getByRole("button", { name: m.correctionSave });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText(m.correctionNote), "Falscher Kontakt");
    await userEvent.click(save);
    await screen.findByRole("button", { name: m.correct });
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls).toEqual(["/api/bff/mail/messages/m1/preparation/correct", "/api/bff/mail/messages/m1/preparation"]);
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ contact_id: "c1", unit_id: "u1", property_id: "p1", note: "Falscher Kontakt" });
  });

  it("shows the API error of a failed computation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Fehler", status: 500, detail: "KI nicht freigegeben" }, 500));
    renderIntl(<PreparationCard message={msg()} onDraftCreated={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: m.compute }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(m.empty)).toBeInTheDocument();
  });
});
