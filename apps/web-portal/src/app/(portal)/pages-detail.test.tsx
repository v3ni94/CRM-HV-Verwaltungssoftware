import { screen } from "@testing-library/react";
import type { ReactElement } from "react";

import { renderIntl } from "@/test/intl";
import { de, requestedPaths, resetRoutes, route, stubProps } from "@/test/serverPage";

vi.mock("@/lib/api-server", async () => (await import("@/test/serverPage")).apiServerMock());
vi.mock("next/navigation", async () => (await import("@/test/serverPage")).navigationMock());
vi.mock("next-intl/server", async () => (await import("@/test/serverPage")).intlServerMock());
vi.mock("@/components/portal/PortalNotifications", async () => (await import("@/test/serverPage")).stubModule(["PortalNotifications"]));
vi.mock("@/components/portal/StartTiles", async () => (await import("@/test/serverPage")).stubModule(["StartTiles"]));
vi.mock("@/components/portal/DocumentBundleList", async () => (await import("@/test/serverPage")).stubModule(["DocumentBundleList"]));
vi.mock("@/components/portal/WorkOrderDetail", async () => (await import("@/test/serverPage")).stubModule(["WorkOrderDetail"]));
vi.mock("@/components/portal/NewTicket", async () => (await import("@/test/serverPage")).stubModule(["NewTicket"]));
vi.mock("@/components/portal/AppointmentProposals", async () => (await import("@/test/serverPage")).stubModule(["AppointmentProposals"]));
vi.mock("@/components/portal/PortalChat", async () => (await import("@/test/serverPage")).stubModule(["PortalChat"]));
vi.mock("@/components/portal/TicketComments", async () => (await import("@/test/serverPage")).stubModule(["TicketComments"]));
vi.mock("@/components/portal/WorkOrderRating", async () => (await import("@/test/serverPage")).stubModule(["WorkOrderRating"]));
vi.mock("@/components/portal/SepaMandateForm", async () => (await import("@/test/serverPage")).stubModule(["SepaMandateForm"]));
vi.mock("@/components/portal/ProviderInfo", async () => (await import("@/test/serverPage")).stubModule(["ProviderInfo"]));
vi.mock("@/components/portal/SecuritySettings", async () => (await import("@/test/serverPage")).stubModule(["SecuritySettings"]));
vi.mock("@/components/portal/SupportConsent", async () => (await import("@/test/serverPage")).stubModule(["SupportConsent"]));
vi.mock("@/components/portal/BoardEngagementDetail", async () => (await import("@/test/serverPage")).stubModule(["BoardEngagementDetail"]));
vi.mock("@/components/portal/MeterReadingForm", async () => (await import("@/test/serverPage")).stubModule(["MeterReadingForm"]));
vi.mock("@/components/portal/DataChangeForm", async () => (await import("@/test/serverPage")).stubModule(["DataChangeForm"]));
vi.mock("@/components/portal/PortalAssistant", async () => (await import("@/test/serverPage")).stubModule(["PortalAssistant"]));
vi.mock("@/components/portal/CircularVotePanel", async () => (await import("@/test/serverPage")).stubModule(["CircularVotePanel"]));
vi.mock("@/components/handover/HandoverFill", async () => (await import("@/test/serverPage")).stubModule(["HandoverFill"]));
vi.mock("@/components/handover/HandoverReadCard", async () => (await import("@/test/serverPage")).stubModule(["HandoverReadCard"]));

import AssistentPage from "./assistent/page";
import AuftraegeDetailPage from "./auftraege/[id]/page";
import AuftraegePage from "./auftraege/page";
import DatenPage from "./daten/page";
import DokumentePage from "./dokumente/page";
import KontoPage from "./konto/page";
import LastschriftPage from "./lastschrift/page";
import MeldungenDetailPage from "./meldungen/[id]/page";
import MeldungenPage from "./meldungen/page";
import PruefungDetailPage from "./pruefung/[id]/page";
import PruefungPage from "./pruefung/page";
import RahmenvertraegePage from "./rahmenvertraege/page";
import SicherheitPage from "./sicherheit/page";
import StartPage from "./start/page";
import UebergabeDetailPage from "./uebergabe/[id]/page";
import UebergabePage from "./uebergabe/page";
import UmlaufbeschluessePage from "./umlaufbeschluesse/page";
import ZaehlerstandPage from "./zaehlerstand/page";

async function show(Page: unknown, props: unknown = {}) {
  let element = await (Page as (p: unknown) => Promise<ReactElement>)(props);
  // A page may return an async child component (uebergabe): resolve it like the server does.
  while (typeof element.type === "function" && element.type.constructor.name === "AsyncFunction") {
    element = await (element.type as (p: unknown) => Promise<ReactElement>)(element.props);
  }
  return renderIntl(element);
}
const params = (id: string) => ({ params: Promise.resolve({ id }) });
const search = (q: Record<string, string | undefined> = {}) => ({ searchParams: Promise.resolve(q) });

beforeEach(() => resetRoutes());

describe("Seiten ohne Daten", () => {
  it.each([
    ["assistent", AssistentPage, "Assistant", "PortalAssistant"],
    ["daten", DatenPage, "DataChange", "DataChangeForm"],
    ["umlaufbeschluesse", UmlaufbeschluessePage, "PortalCircular", "CircularVotePanel"],
    ["zaehlerstand", ZaehlerstandPage, "Meter", "MeterReadingForm"],
  ])("%s: title and form, no API call", async (_n, Page, ns, stub) => {
    await show(Page);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(de(ns, "title"));
    expect(screen.getByTestId(stub)).toBeInTheDocument();
    expect(requestedPaths).toEqual([]);
  });
});

describe("start", () => {
  const me = (roles: string[]) => ({ contact_id: "c", roles, contracts: [] });

  it("counts new notices for tenants", async () => {
    route("/api/v1/portal/me", 200, me(["tenant"]));
    route("/api/v1/portal/notices", 200, [{ is_new: true }, { is_new: false }, { is_new: true }]);
    await show(StartPage);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Übersicht");
    expect(stubProps(screen.getByTestId("StartTiles"))).toMatchObject({ newNotices: 2, me: { roles: ["tenant"] } });
  });

  it("does not load notices for providers", async () => {
    route("/api/v1/portal/me", 200, me(["provider"]));
    await show(StartPage);
    expect(requestedPaths).toEqual(["/api/v1/portal/me"]);
    expect(stubProps(screen.getByTestId("StartTiles"))).toMatchObject({ newNotices: 0 });
  });

  it("hides only the hint when the notice call fails", async () => {
    route("/api/v1/portal/me", 200, me(["owner"]));
    route("/api/v1/portal/notices", 500);
    await show(StartPage);
    expect(stubProps(screen.getByTestId("StartTiles"))).toMatchObject({ newNotices: 0 });
  });

  it("ends the session on 401 and raises an error on 500", async () => {
    route("/api/v1/portal/me", 401);
    await expect(show(StartPage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
    route("/api/v1/portal/me", 500);
    await expect(show(StartPage)).rejects.toThrow();
  });
});

describe("dokumente", () => {
  const docs = [{ id: "d1", title: "Mietvertrag" }];

  it("lists documents and shows staff handovers only on 200", async () => {
    route("/api/v1/portal/documents", 200, docs);
    route("/api/v1/portal/handovers", 200, [
      { id: "h1", number: "UE-1", status: "draft", address: "Musterstr. 1", handover_date: "2026-03-05T10:00:00Z" },
    ]);
    await show(DokumentePage, search());
    expect(stubProps(screen.getByTestId("DocumentBundleList"))).toMatchObject({ rows: docs });
    expect(screen.getByRole("link", { name: /UE-1/ })).toHaveAttribute("href", "/uebergabe/h1");
    expect(screen.getByText(/05\.03\.2026/)).toBeInTheDocument();
  });

  it("hides the handover block for external users (403)", async () => {
    route("/api/v1/portal/documents", 200, docs);
    route("/api/v1/portal/handovers", 403);
    await show(DokumentePage, search());
    expect(screen.queryByText(de("Documents", "handoversTitle"))).not.toBeInTheDocument();
  });

  it("shows the empty notice without documents", async () => {
    route("/api/v1/portal/documents", 200, []);
    route("/api/v1/portal/handovers", 200, []);
    await show(DokumentePage, search({ q: "x", sort: "title_asc" }));
    expect(screen.getByText(de("Documents", "empty"))).toBeInTheDocument();
    expect(screen.getByText(de("Documents", "handoversEmpty"))).toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toHaveValue("x");
    expect(screen.getByRole("combobox")).toHaveValue("title_asc");
  });

  it("falls back to the default sort for unknown values and shortens the search", async () => {
    route("/api/v1/portal/documents", 200, []);
    route("/api/v1/portal/handovers", 403);
    await show(DokumentePage, search({ q: "a".repeat(150), sort: "evil" }));
    expect(screen.getByRole("combobox")).toHaveValue("created_desc");
    expect((screen.getByRole("searchbox") as HTMLInputElement).value).toHaveLength(100);
  });

  it("ends the session on 401, raises an error on 500", async () => {
    route("/api/v1/portal/documents", 401);
    await expect(show(DokumentePage, search())).rejects.toThrow("NEXT_REDIRECT:/anmelden");
    route("/api/v1/portal/documents", 500, { detail: "boom" });
    await expect(show(DokumentePage, search())).rejects.toThrow();
  });
});

describe("konto", () => {
  it("shows open items with German date and amount format", async () => {
    route("/api/v1/portal/account", 200, {
      note: "Stand heute",
      items: [{ contract_number: "M-100", due_date: "2026-04-01", amount: "1234.5", remaining: "0.5" }],
    });
    await show(KontoPage);
    expect(screen.getByText("Stand heute")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "M-100" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "01.04.2026" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "1.234,50 EUR" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "0,50 EUR" })).toBeInTheDocument();
  });

  it("shows the empty notice and no table without items", async () => {
    route("/api/v1/portal/account", 200, { note: null, items: [] });
    await show(KontoPage);
    expect(screen.getByText(de("Account", "empty"))).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("ends the session on 401, raises an error on 500", async () => {
    route("/api/v1/portal/account", 401);
    await expect(show(KontoPage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
    route("/api/v1/portal/account", 500);
    await expect(show(KontoPage)).rejects.toThrow();
  });
});

describe("auftraege", () => {
  const orders = [
    { id: "o1", description: "Heizung prüfen", status: "requested" },
    { id: "o2", description: "Dach", status: "done" },
  ];

  it("lists orders with status badge and link", async () => {
    route("/api/v1/portal/work-orders", 200, orders);
    await show(AuftraegePage);
    expect(screen.getByRole("link", { name: /Heizung prüfen/ })).toHaveAttribute("href", "/auftraege/o1");
    expect(screen.getByRole("link", { name: /Dach/ })).toHaveAttribute("href", "/auftraege/o2");
  });

  it("shows the empty notice", async () => {
    route("/api/v1/portal/work-orders", 200, []);
    await show(AuftraegePage);
    expect(screen.getByText(de("Orders", "empty"))).toBeInTheDocument();
  });

  it("detail: passes the matching order, unknown id is 404", async () => {
    route("/api/v1/portal/work-orders", 200, orders);
    await show(AuftraegeDetailPage, params("o2"));
    expect(stubProps(screen.getByTestId("WorkOrderDetail"))).toMatchObject({ order: { id: "o2" } });
    expect(screen.getByRole("link", { name: de("Orders", "back") })).toHaveAttribute("href", "/auftraege");
    await expect(show(AuftraegeDetailPage, params("fremd"))).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("ends the session on 401, raises an error on 500", async () => {
    route("/api/v1/portal/work-orders", 401);
    await expect(show(AuftraegePage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
    await expect(show(AuftraegeDetailPage, params("o1"))).rejects.toThrow("NEXT_REDIRECT:/anmelden");
    route("/api/v1/portal/work-orders", 500);
    await expect(show(AuftraegePage)).rejects.toThrow();
  });
});

describe("meldungen", () => {
  const ticket = {
    id: "t1",
    number: "T-7",
    title: "Wasserhahn tropft",
    status: "new",
    comments: ["a", "b"],
    attachments: [{ id: "f1", filename: "foto.jpg" }],
    appointment_proposals: [{ id: "p1", status: "proposed" }],
    completed_work_order_ids: ["o9"],
  };

  it("lists tickets with the form, appointment hint and history count", async () => {
    route("/api/v1/portal/tickets", 200, [ticket]);
    await show(MeldungenPage);
    expect(screen.getByTestId("NewTicket")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Wasserhahn tropft/ });
    expect(link).toHaveAttribute("href", "/meldungen/t1");
    expect(link).toHaveTextContent(de("Tickets", "appointmentsOpen"));
    expect(link).toHaveTextContent("2");
  });

  it("shows the empty notice", async () => {
    route("/api/v1/portal/tickets", 200, []);
    await show(MeldungenPage);
    expect(screen.getByText(de("Tickets", "empty"))).toBeInTheDocument();
  });

  it("detail: shows comments without chat, rating for finished orders, attachments", async () => {
    route("/api/v1/portal/tickets", 200, [ticket]);
    route("/api/v1/portal/me", 200, { features: { chat_enabled: false } });
    await show(MeldungenDetailPage, params("t1"));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("T-7: Wasserhahn tropft");
    expect(screen.getByText("foto.jpg")).toBeInTheDocument();
    expect(stubProps(screen.getByTestId("WorkOrderRating"))).toMatchObject({ orderId: "o9" });
    expect(stubProps(screen.getByTestId("TicketComments"))).toMatchObject({ ticketId: "t1", comments: ["a", "b"] });
    expect(screen.queryByTestId("PortalChat")).not.toBeInTheDocument();
  });

  it("detail: switches to the chat when the tenant enabled it", async () => {
    route("/api/v1/portal/tickets", 200, [ticket]);
    route("/api/v1/portal/me", 200, { features: { chat_enabled: true } });
    await show(MeldungenDetailPage, params("t1"));
    expect(stubProps(screen.getByTestId("PortalChat"))).toMatchObject({ ticketId: "t1" });
    expect(screen.queryByTestId("TicketComments")).not.toBeInTheDocument();
  });

  it("detail: a foreign ticket id is 404, 401 ends the session", async () => {
    route("/api/v1/portal/tickets", 200, [ticket]);
    route("/api/v1/portal/me", 200, {});
    await expect(show(MeldungenDetailPage, params("fremd"))).rejects.toThrow("NEXT_NOT_FOUND");
    route("/api/v1/portal/tickets", 401);
    await expect(show(MeldungenDetailPage, params("t1"))).rejects.toThrow("NEXT_REDIRECT:/anmelden");
    await expect(show(MeldungenPage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
  });
});

describe("lastschrift", () => {
  it("passes contracts and own proposals to the form", async () => {
    route("/api/v1/portal/me", 200, { contracts: [{ id: "k1", kind: "rental", number: "M-1" }] });
    route("/api/v1/portal/sepa-mandates", 200, [{ id: "m1" }]);
    await show(LastschriftPage);
    expect(stubProps(screen.getByTestId("SepaMandateForm"))).toMatchObject({
      contracts: [{ id: "k1", kind: "rental", number: "M-1" }],
      proposals: [{ id: "m1" }],
    });
  });

  it("uses empty lists when the mandates are not available", async () => {
    route("/api/v1/portal/me", 500);
    route("/api/v1/portal/sepa-mandates", 403);
    await show(LastschriftPage);
    expect(stubProps(screen.getByTestId("SepaMandateForm"))).toMatchObject({ contracts: [], proposals: [] });
  });

  it("ends the session on 401", async () => {
    route("/api/v1/portal/me", 401);
    await expect(show(LastschriftPage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
  });
});

describe("rahmenvertraege", () => {
  it("passes contracts and availability to the provider view", async () => {
    route("/api/v1/portal/provider/framework-contracts", 200, [{ id: "r1" }]);
    route("/api/v1/portal/provider/availability", 200, [{ id: "w1" }]);
    await show(RahmenvertraegePage);
    expect(stubProps(screen.getByTestId("ProviderInfo"))).toMatchObject({ contracts: [{ id: "r1" }], windows: [{ id: "w1" }] });
  });

  it("raises an error when one of both calls is refused", async () => {
    route("/api/v1/portal/provider/framework-contracts", 200, []);
    route("/api/v1/portal/provider/availability", 403);
    await expect(show(RahmenvertraegePage)).rejects.toThrow();
  });

  it("ends the session on 401", async () => {
    route("/api/v1/portal/provider/framework-contracts", 401);
    route("/api/v1/portal/provider/availability", 200, []);
    await expect(show(RahmenvertraegePage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
  });
});

describe("sicherheit", () => {
  function base(consent: unknown, consentStatus = 200, passkeys: unknown = { available: true }) {
    route("/api/v1/auth/me", 200, { totp_enabled: true, mfa_required: true });
    route("/api/v1/auth/trusted-devices", 200, [{ id: "dv1" }]);
    route("/api/v1/portal/support-consent", consentStatus, consent);
    route("/api/v1/auth/webauthn/status", 200, passkeys);
  }

  it("passes the factor state, devices and passkey availability on", async () => {
    base({ active: false, expires_at: null, available: true });
    await show(SicherheitPage);
    expect(stubProps(screen.getByTestId("SecuritySettings"))).toMatchObject({
      totpEnabled: true,
      initialDevices: [{ id: "dv1" }],
      passkeysAvailable: true,
      mfaRequired: true,
    });
    expect(screen.getByTestId("SupportConsent")).toBeInTheDocument();
  });

  it("hides the support consent when it is not available or the call fails", async () => {
    base({ active: false, expires_at: null, available: false });
    await show(SicherheitPage);
    expect(screen.queryByTestId("SupportConsent")).not.toBeInTheDocument();
  });

  it("treats failing consent and passkey calls as unavailable", async () => {
    base(undefined, 500, { available: false });
    await show(SicherheitPage);
    expect(screen.queryByTestId("SupportConsent")).not.toBeInTheDocument();
    expect(stubProps(screen.getByTestId("SecuritySettings"))).toMatchObject({ passkeysAvailable: false });
  });

  it("ends the session on 401", async () => {
    base({ available: false });
    route("/api/v1/auth/me", 401);
    await expect(show(SicherheitPage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
  });
});

describe("uebergabe", () => {
  it("lists all protocols for staff", async () => {
    route("/api/v1/portal/handover/protocols", 200, [
      { id: "h1", number: "UE-1", status: "draft", address: "Weg 1", handover_date: "2026-05-02T08:00:00Z" },
    ]);
    await show(UebergabePage);
    expect(screen.getByRole("link", { name: /UE-1/ })).toHaveAttribute("href", "/uebergabe/h1");
    expect(requestedPaths).toEqual(["/api/v1/portal/handover/protocols"]);
    expect(screen.getByText(/02\.05\.2026/)).toBeInTheDocument();
  });

  it("falls back to the grant based list for participants with access hints", async () => {
    route("/api/v1/portal/handover/protocols", 403);
    route("/api/v1/portal/handover", 200, [
      { id: "h2", number: "UE-2", version: 2, status: "completed", locked: true, address: "", handover_date: null, right: "read", valid_to: "2026-12-31T00:00:00Z" },
      { id: "h3", number: "UE-3", version: 1, status: "in_progress", locked: false, address: "Weg 3", handover_date: null, right: "edit", valid_to: null },
    ]);
    await show(UebergabePage);
    expect(screen.getByRole("link", { name: /UE-2 V2/ })).toHaveTextContent("31.12.2026");
    expect(screen.getByRole("link", { name: /UE-3/ })).toHaveTextContent("Weg 3");
  });

  it("shows the empty notice without grants and raises an error on 500", async () => {
    route("/api/v1/portal/handover/protocols", 403);
    route("/api/v1/portal/handover", 200, []);
    await show(UebergabePage);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Übergabeprotokolle");
    route("/api/v1/portal/handover", 500);
    await expect(show(UebergabePage)).rejects.toThrow();
  });

  it("ends the session on 401", async () => {
    route("/api/v1/portal/handover/protocols", 401);
    await expect(show(UebergabePage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
  });

  it("detail: read right shows the read card, edit right the form", async () => {
    route("/api/v1/portal/handover/p1", 200, { id: "p1", number: "UE-1", version: 3, address: "Weg 1", access: { right: "read" } });
    await show(UebergabeDetailPage, params("p1"));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("UE-1 V3");
    expect(stubProps(screen.getByTestId("HandoverReadCard"))).toMatchObject({ files: "/api/portal-files/portal/handover/p1" });
    expect(screen.queryByTestId("HandoverFill")).not.toBeInTheDocument();
  });

  it("detail: edit right, unknown protocol 404, 500 raises an error", async () => {
    route("/api/v1/portal/handover/p2", 200, { id: "p2", number: "UE-2", version: 1, address: "", access: { right: "edit" } });
    await show(UebergabeDetailPage, params("p2"));
    expect(screen.getByTestId("HandoverFill")).toBeInTheDocument();
    route("/api/v1/portal/handover/x", 404);
    await expect(show(UebergabeDetailPage, params("x"))).rejects.toThrow("NEXT_NOT_FOUND");
    route("/api/v1/portal/handover/y", 500);
    await expect(show(UebergabeDetailPage, params("y"))).rejects.toThrow();
  });
});

describe("pruefung", () => {
  const row = {
    id: "e1",
    legal_entity_id: "le1",
    legal_entity_name: "WEG Musterstraße",
    sampling: "sample",
    purpose: "Jahresprüfung",
    period_from: "2025-01-01",
    period_to: "2025-12-31",
    open_questions: 3,
  };

  it("lists engagements with period and open questions", async () => {
    route("/api/v1/portal/board/engagements", 200, [row]);
    await show(PruefungPage);
    const link = screen.getByRole("link", { name: /WEG Musterstraße/ });
    expect(link).toHaveAttribute("href", "/pruefung/e1");
    expect(link).toHaveTextContent("01.01.2025");
    expect(link).toHaveTextContent("31.12.2025");
  });

  it("shows the empty notice when the API refuses (no board role)", async () => {
    route("/api/v1/portal/board/engagements", 403);
    await show(PruefungPage);
    expect(screen.getByText(de("Audit", "empty"))).toBeInTheDocument();
  });

  it("ends the session on 401", async () => {
    route("/api/v1/portal/board/engagements", 401);
    await expect(show(PruefungPage)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
  });

  const base = "/api/v1/portal/board/engagements/e1";

  it("detail: loads the engagement with filter and the reports", async () => {
    route(`${base}?date_from=2025-01-01&q=Strom`, 200, { id: "e1" });
    route(`${base}/reports`, 200, [{ id: "rep1" }]);
    await show(PruefungDetailPage, { ...params("e1"), ...search({ q: " Strom ", date_from: "2025-01-01", evil: "1" }) });
    expect(requestedPaths[0]).toBe(`${base}?date_from=2025-01-01&q=Strom`);
    expect(stubProps(screen.getByTestId("BoardEngagementDetail"))).toMatchObject({ detail: { id: "e1" }, reports: [{ id: "rep1" }] });
  });

  it("detail: an invalid filter (422) shows the unfiltered engagement with a hint", async () => {
    route(`${base}?date_from=2025-12-31&date_to=2025-01-01`, 422, { detail: "range" });
    route(base, 200, { id: "e1" });
    route(`${base}/reports`, 500);
    await show(PruefungDetailPage, { ...params("e1"), ...search({ date_from: "2025-12-31", date_to: "2025-01-01" }) });
    expect(screen.getByRole("alert")).toHaveTextContent("Der Filter ist ungültig");
    expect(stubProps(screen.getByTestId("BoardEngagementDetail"))).toMatchObject({ detail: { id: "e1" }, reports: [] });
  });

  it("detail: a foreign engagement is 404, also after a 422", async () => {
    route(base, 404);
    await expect(show(PruefungDetailPage, { ...params("e1"), ...search() })).rejects.toThrow("NEXT_NOT_FOUND");
    route(`${base}?q=x`, 422);
    await expect(show(PruefungDetailPage, { ...params("e1"), ...search({ q: "x" }) })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("detail: 401 ends the session, 500 raises an error", async () => {
    route(base, 401);
    await expect(show(PruefungDetailPage, { ...params("e1"), ...search() })).rejects.toThrow("NEXT_REDIRECT:/anmelden");
    route(base, 500);
    await expect(show(PruefungDetailPage, { ...params("e1"), ...search() })).rejects.toThrow("500");
  });
});
