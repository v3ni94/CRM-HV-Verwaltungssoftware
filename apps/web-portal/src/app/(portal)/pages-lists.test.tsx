import { screen } from "@testing-library/react";
import type { ReactElement } from "react";

import { renderIntl } from "@/test/intl";
import { de, requestedPaths, resetRoutes, route, stubProps } from "@/test/serverPage";

vi.mock("@/lib/api-server", async () => (await import("@/test/serverPage")).apiServerMock());
vi.mock("next/navigation", async () => (await import("@/test/serverPage")).navigationMock());
vi.mock("next-intl/server", async () => (await import("@/test/serverPage")).intlServerMock());
vi.mock("@/components/portal/ResolutionList", async () => (await import("@/test/serverPage")).stubModule(["ResolutionList"]));
vi.mock("@/components/portal/PropertyContactList", async () => (await import("@/test/serverPage")).stubModule(["PropertyContactList"]));
vi.mock("@/components/portal/HoaAccountTable", async () => (await import("@/test/serverPage")).stubModule(["HoaAccountTable"]));
vi.mock("@/components/portal/MeetingList", async () => (await import("@/test/serverPage")).stubModule(["MeetingList"]));
vi.mock("@/components/portal/OwnerRentalReporting", async () => (await import("@/test/serverPage")).stubModule(["OwnerRentalReporting"]));
vi.mock("@/components/portal/OwnerReports", async () =>
  (await import("@/test/serverPage")).stubModule(["OwnerPlanList", "OwnerStatementExplanations"]),
);
vi.mock("@/components/portal/OwnerOverview", async () => (await import("@/test/serverPage")).stubModule(["OwnerOverview"]));
vi.mock("@/components/portal/ConsumptionInfoList", async () => (await import("@/test/serverPage")).stubModule(["ConsumptionInfoList"]));
vi.mock("@/components/portal/NoticeList", async () => (await import("@/test/serverPage")).stubModule(["NoticeList"]));
vi.mock("@/components/portal/PortalForms", async () => (await import("@/test/serverPage")).stubModule(["PortalForms"]));
vi.mock("@/components/portal/TenantStatements", async () =>
  (await import("@/test/serverPage")).stubModule(["TenantStatementList", "TenantStatementDetail"]),
);
vi.mock("@/components/portal/RepresentationList", async () => (await import("@/test/serverPage")).stubModule(["RepresentationList"]));
vi.mock("@/components/portal/BoardSubmissions", async () => (await import("@/test/serverPage")).stubModule(["BoardSubmissions"]));

import AbrechnungenPage from "./abrechnungen/page";
import AnsprechpartnerPage from "./ansprechpartner/page";
import AushaengePage from "./aushaenge/page";
import BelegePage from "./belege/page";
import BeschluessePage from "./beschluesse/page";
import EigentuemerabrechnungenPage from "./eigentuemerabrechnungen/page";
import EigentumPage from "./eigentum/page";
import FormularePage from "./formulare/page";
import HausgeldkontoPage from "./hausgeldkonto/page";
import NebenkostenPage from "./nebenkosten/page";
import NebenkostenDetailPage from "./nebenkosten/[statementId]/[contractId]/page";
import ReportingPage from "./reporting/page";
import VerbrauchPage from "./verbrauch/page";
import VersammlungenPage from "./versammlungen/page";
import VertretungPage from "./vertretung/page";
import VorlagenPage from "./vorlagen/page";
import WirtschaftsplaenePage from "./wirtschaftsplaene/page";

type PageFn = (props: never) => Promise<ReactElement>;

async function show(Page: PageFn, props: unknown = { searchParams: Promise.resolve({}) }) {
  return renderIntl(await (Page as unknown as (p: unknown) => Promise<ReactElement>)(props));
}

beforeEach(() => resetRoutes());

/** Pages that answer 403 for non owners with a notice instead of the list. */
const OWNER_PAGES: {
  name: string;
  Page: PageFn;
  path: string;
  ns: string;
  key: string;
  title: string;
  body: unknown;
  stub: string;
  props: Record<string, unknown>;
}[] = [
  { name: "beschluesse", Page: BeschluessePage, path: "/api/v1/portal/resolutions", ns: "Resolutions", key: "ownersOnly", title: "Resolutions", body: [{ id: "r1" }], stub: "ResolutionList", props: { rows: [{ id: "r1" }] } },
  { name: "ansprechpartner", Page: AnsprechpartnerPage, path: "/api/v1/portal/property-contacts", ns: "Contacts", key: "ownersOnly", title: "Contacts", body: [{ id: "p1" }], stub: "PropertyContactList", props: { rows: [{ id: "p1" }] } },
  { name: "hausgeldkonto", Page: HausgeldkontoPage, path: "/api/v1/portal/hoa-account", ns: "HoaAccount", key: "ownersOnly", title: "HoaAccount", body: { lines: [] }, stub: "HoaAccountTable", props: { account: { lines: [] } } },
  { name: "versammlungen", Page: VersammlungenPage, path: "/api/v1/portal/meetings", ns: "Meetings", key: "ownersOnly", title: "Meetings", body: [{ id: "m1" }], stub: "MeetingList", props: { rows: [{ id: "m1" }] } },
  { name: "wirtschaftsplaene", Page: WirtschaftsplaenePage, path: "/api/v1/portal/owner/plans", ns: "OwnerPlans", key: "ownersOnly", title: "OwnerPlans", body: { items: [{ id: "pl1" }], texts: { a: "b" }, note: "Hinweis Plan" }, stub: "OwnerPlanList", props: { items: [{ id: "pl1" }], texts: { a: "b" } } },
  { name: "reporting", Page: ReportingPage, path: "/api/v1/portal/owner/rental-reporting", ns: "OwnerReporting", key: "ownersOnly", title: "OwnerReporting", body: { items: [], note: "N", enabled: true }, stub: "OwnerRentalReporting", props: { items: [], note: "N", enabled: true } },
  { name: "verbrauch", Page: VerbrauchPage, path: "/api/v1/portal/consumption-info", ns: "ConsumptionInfo", key: "locked", title: "ConsumptionInfo", body: [{ id: "c1" }], stub: "ConsumptionInfoList", props: { rows: [{ id: "c1" }] } },
  { name: "belege", Page: BelegePage, path: "/api/v1/portal/owner/receipts", ns: "OwnerReceipts", key: "ownersOnly", title: "OwnerReceipts", body: { items: [], years: [], enabled: false, note: "" }, stub: "", props: {} },
  { name: "abrechnungen", Page: AbrechnungenPage, path: "/api/v1/portal/owner/statements", ns: "OwnerStatements", key: "ownersOnly", title: "OwnerStatements", body: { items: [], note: "" }, stub: "", props: {} },
  { name: "eigentuemerabrechnungen", Page: EigentuemerabrechnungenPage, path: "/api/v1/portal/owner/rental-statements", ns: "OwnerRentalStatements", key: "ownersOnly", title: "OwnerRentalStatements", body: { items: [], note: "Gesperrt", enabled: false }, stub: "", props: {} },
  { name: "eigentum", Page: EigentumPage, path: "/api/v1/portal/owner/payment-resolutions", ns: "OwnerOverview", key: "ownersOnly", title: "OwnerOverview", body: { items: [], note: "Zahlungen" }, stub: "OwnerOverview", props: { payments: [], note: "Zahlungen" } },
];

function routeAllOwnerSideCalls() {
  route("/api/v1/portal/owner/tickets", 200, []);
  route("/api/v1/portal/owner/allocation-properties", 200, { items: [] });
  route("/api/v1/portal/owner/rental-income", 200, { items: [] });
  route("/api/v1/portal/owner/takeover-checklist", 200, { items: [], note: "" });
  route("/api/v1/portal/owner/asset-reports", 200, { items: [], note: "" });
  route("/api/v1/portal/owner/statement-explanations", 200, { items: [], texts: {}, note: "" });
}

describe.each(OWNER_PAGES)("Seite $name", (c) => {
  beforeEach(routeAllOwnerSideCalls);

  it("shows the title and passes the API data on", async () => {
    route(c.path, 200, c.body);
    await show(c.Page);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(de(c.ns, "title"));
    expect(requestedPaths[0]).toBe(c.path);
    if (c.stub) {
      expect(stubProps(screen.getByTestId(c.stub))).toMatchObject(c.props);
    }
  });

  it("answers 403 with the notice for non owners and no data", async () => {
    route(c.path, 403, { detail: "forbidden" });
    await show(c.Page);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(de(c.ns, "title"));
    expect(screen.getByText(de(c.ns, c.key))).toBeInTheDocument();
    if (c.stub) expect(screen.queryByTestId(c.stub)).not.toBeInTheDocument();
  });

  it("ends the session on 401", async () => {
    route(c.path, 401, { detail: "unauthenticated" });
    await expect(show(c.Page)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
  });

  it("raises an error on a server failure instead of showing an empty list", async () => {
    route(c.path, 500, { detail: "boom" });
    await expect(show(c.Page)).rejects.toThrow("HTTP 500");
  });
});

describe("abrechnungen", () => {
  it("lists statements with PDF links, asset reports and explanations", async () => {
    route("/api/v1/portal/owner/statements", 200, {
      items: [{ statement_id: "s1", year: 2025, version: 2, status: "released", unit_id: "u1", unit_number: "W 12" }],
      note: "Nur freigegebene Abrechnungen",
    });
    route("/api/v1/portal/owner/asset-reports", 200, {
      items: [{ report_id: "a1", as_of: "2025-12-31", issued_at: null }],
      note: "",
    });
    route("/api/v1/portal/owner/statement-explanations", 200, { items: [{ id: "e1" }], texts: { k: "v" }, note: "G4 Hinweis" });
    await show(AbrechnungenPage);
    const links = screen.getAllByRole("link", { name: de("OwnerStatements", "download") });
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/api/portal-files/portal/owner/statements/s1/units/u1/pdf",
      "/api/portal-files/portal/owner/asset-reports/a1/pdf",
    ]);
    expect(screen.getByText("Nur freigegebene Abrechnungen")).toBeInTheDocument();
    expect(screen.getByText("G4 Hinweis")).toBeInTheDocument();
    expect(stubProps(screen.getByTestId("OwnerStatementExplanations"))).toMatchObject({ texts: { k: "v" } });
  });

  it("falls back to empty notices when the optional side calls fail", async () => {
    route("/api/v1/portal/owner/statements", 200, { items: [], note: "" });
    route("/api/v1/portal/owner/asset-reports", 500);
    route("/api/v1/portal/owner/statement-explanations", 403);
    await show(AbrechnungenPage);
    expect(screen.getByText(de("OwnerStatements", "empty"))).toBeInTheDocument();
    expect(screen.getByText(de("OwnerStatements", "assetEmpty"))).toBeInTheDocument();
  });
});

describe("belege", () => {
  const body = {
    items: [
      { statement_id: "s1", year: 2025, version: 1, item_id: "i1", label: "Hausmeister", amount: "1234.50", document_id: "d1", document_title: "R1", available: true },
      { statement_id: "s1", year: 2025, version: 1, item_id: "i2", label: "Strom", amount: "99.00", document_id: null, document_title: null, available: false },
    ],
    years: [2025],
    enabled: true,
    note: "Abruf wird vermerkt",
  };

  it("links available receipts, marks missing ones and formats the amount", async () => {
    route("/api/v1/portal/owner/receipts", 200, body);
    await show(BelegePage, { searchParams: Promise.resolve({}) });
    expect(screen.getByRole("link", { name: de("OwnerReceipts", "open") })).toHaveAttribute(
      "href",
      "/api/portal-files/portal/documents/d1/download",
    );
    expect(screen.getByText(de("OwnerReceipts", "unavailable"))).toBeInTheDocument();
    expect(screen.getByText(/1\.234,50/)).toBeInTheDocument();
  });

  it("passes only a valid year and a trimmed, shortened search term to the API", async () => {
    route("/api/v1/portal/owner/receipts?year=2025&q=Strom", 200, body);
    await show(BelegePage, { searchParams: Promise.resolve({ year: "2025", q: "  Strom  " }) });
    expect(requestedPaths).toEqual(["/api/v1/portal/owner/receipts?year=2025&q=Strom"]);
  });

  it("drops a malformed year parameter", async () => {
    route("/api/v1/portal/owner/receipts", 200, body);
    await show(BelegePage, { searchParams: Promise.resolve({ year: "20x5", q: "   " }) });
    expect(requestedPaths).toEqual(["/api/v1/portal/owner/receipts"]);
  });

  it("shows the disabled notice and no search form when the tenant switch is off", async () => {
    route("/api/v1/portal/owner/receipts", 200, { ...body, items: [], enabled: false });
    await show(BelegePage, { searchParams: Promise.resolve({}) });
    expect(screen.getByText(de("OwnerReceipts", "disabled"))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: de("OwnerReceipts", "submit") })).not.toBeInTheDocument();
  });
});

describe("eigentuemerabrechnungen", () => {
  it("shows statements with formatted amounts when enabled", async () => {
    route("/api/v1/portal/owner/rental-statements", 200, {
      enabled: true,
      note: "Freigegeben",
      items: [
        { statement_id: "x1", kind: "rental_owner", period_from: "2025-01-01", period_to: "2025-12-31", property_name: "Haus A", income_total: "12000.00", expenses_total: "2000.00", payouts_total: null },
      ],
    });
    await show(EigentuemerabrechnungenPage);
    expect(screen.getByText("Haus A")).toBeInTheDocument();
    expect(screen.getByText(/12\.000,00/)).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/api/portal-files/portal/owner/rental-statements/x1/pdf");
  });

  it("shows only the note as notice while the feature is off", async () => {
    route("/api/v1/portal/owner/rental-statements", 200, { enabled: false, note: "Noch nicht freigegeben", items: [] });
    await show(EigentuemerabrechnungenPage);
    expect(screen.getByText("Noch nicht freigegeben")).toBeInTheDocument();
    expect(screen.queryByText(de("OwnerRentalStatements", "empty"))).not.toBeInTheDocument();
  });
});

describe("eigentum", () => {
  it("tolerates failing optional side calls", async () => {
    route("/api/v1/portal/owner/payment-resolutions", 200, { items: [{ id: "p1" }], note: "N" });
    for (const p of ["owner/tickets", "owner/allocation-properties", "owner/rental-income", "owner/takeover-checklist"]) {
      route(`/api/v1/portal/${p}`, 500);
    }
    await show(EigentumPage);
    expect(stubProps(screen.getByTestId("OwnerOverview"))).toMatchObject({
      payments: [{ id: "p1" }],
      tickets: [],
      allocations: [],
      income: [],
      takeover: [],
    });
  });
});

describe("Seiten mit einfacher Liste", () => {
  const SIMPLE: { name: string; Page: PageFn; path: string; ns: string; stub: string; body: unknown; props: Record<string, unknown> }[] = [
    { name: "aushaenge", Page: AushaengePage, path: "/api/v1/portal/notices", ns: "Notices", stub: "NoticeList", body: [{ id: "n1" }], props: { notices: [{ id: "n1" }] } },
    { name: "formulare", Page: FormularePage, path: "/api/v1/portal/forms", ns: "Forms", stub: "PortalForms", body: [{ code: "f1" }], props: { forms: [{ code: "f1" }] } },
    { name: "nebenkosten", Page: NebenkostenPage, path: "/api/v1/portal/tenant-statements", ns: "TenantStatements", stub: "TenantStatementList", body: { items: [{ id: "t1" }], note: "Hinweis" }, props: { items: [{ id: "t1" }], note: "Hinweis" } },
    { name: "vertretung", Page: VertretungPage, path: "/api/v1/portal/representations", ns: "Representation", stub: "RepresentationList", body: { items: [{ id: "v1" }] }, props: { rows: [{ id: "v1" }] } },
  ];

  it.each(SIMPLE)("$name: renders the title and passes the data on", async (c) => {
    route(c.path, 200, c.body);
    await show(c.Page);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(de(c.ns, "title"));
    expect(stubProps(screen.getByTestId(c.stub))).toMatchObject(c.props);
  });

  it.each(SIMPLE)("$name: 401 ends the session, 500 raises an error", async (c) => {
    route(c.path, 401);
    await expect(show(c.Page)).rejects.toThrow("NEXT_REDIRECT:/anmelden");
    route(c.path, 500);
    await expect(show(c.Page)).rejects.toThrow();
  });

  it("aushaenge: 403 is an error, not an empty list", async () => {
    route("/api/v1/portal/notices", 403);
    await expect(show(AushaengePage)).rejects.toThrow("403");
  });
});

describe("vorlagen", () => {
  it("passes the submissions to the form", async () => {
    route("/api/v1/portal/board/submissions", 200, [{ id: "b1" }]);
    await show(VorlagenPage);
    expect(screen.getByText(de("BoardSubmissions", "roleNotice"))).toBeInTheDocument();
    expect(stubProps(screen.getByTestId("BoardSubmissions"))).toMatchObject({ initial: [{ id: "b1" }] });
  });

  it("starts with an empty list when the API refuses (no board role)", async () => {
    route("/api/v1/portal/board/submissions", 403);
    await show(VorlagenPage);
    expect(stubProps(screen.getByTestId("BoardSubmissions"))).toMatchObject({ initial: [] });
  });
});

describe("nebenkosten/[statementId]/[contractId]", () => {
  const S = "11111111-1111-1111-1111-111111111111";
  const C = "22222222-2222-2222-2222-222222222222";
  const path = `/api/v1/portal/tenant-statements/${S}/contracts/${C}`;
  const params = (statementId: string, contractId: string) => ({ params: Promise.resolve({ statementId, contractId }) });

  it("renders the detail", async () => {
    route(path, 200, { id: "detail" });
    await show(NebenkostenDetailPage, params(S, C));
    expect(stubProps(screen.getByTestId("TenantStatementDetail"))).toMatchObject({ data: { id: "detail" } });
  });

  it("rejects malformed ids as not found without calling the API", async () => {
    await expect(show(NebenkostenDetailPage, params("../x", C))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(requestedPaths).toEqual([]);
  });

  it("maps 404 to not found, 403 to the locked notice and 500 to an error", async () => {
    route(path, 404);
    await expect(show(NebenkostenDetailPage, params(S, C))).rejects.toThrow("NEXT_NOT_FOUND");
    route(path, 403);
    await show(NebenkostenDetailPage, params(S, C));
    expect(screen.getByText(de("TenantStatements", "locked"))).toBeInTheDocument();
    expect(screen.queryByTestId("TenantStatementDetail")).not.toBeInTheDocument();
    route(path, 500);
    await expect(show(NebenkostenDetailPage, params(S, C))).rejects.toThrow("HTTP 500");
  });
});
