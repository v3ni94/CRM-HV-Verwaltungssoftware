import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BusinessRulesList } from "./BusinessRulesList";

const ALL = [
  "tenant_settings:read",
  "tenant_settings:update",
  "accounting:read",
  "accounting:update",
  "accounting:approve",
  "contracts:read",
  "contracts:update",
  "tickets:read",
  "documents:read",
  "contacts:approve",
];

const DOCS = {
  "accounting/rent-invoices/numbering-mode": { mode: "draft_numbers", modes: ["draft_numbers"], hinweis: "x" },
  "accounting/tax/settings": {
    input_tax_enabled: false,
    input_tax_account_number: null,
    construction_withholding_enabled: false,
    construction_withholding_percent: "15.00",
    section_35a_enabled: false,
    approval_limits_enabled: false,
    approval_limits: [],
    subledger_exclude_written_off: true,
  },
  "accounting/period-locks/settings": { lock_mode: "ledger_only", auto_lock_on_close: false, reopen_enabled: false },
  "accounting/templates": [{ version: 3, four_eyes_required: true }],
  "accounting/rule-versions/checkpoints": [],
  "billing/advance-rule": { surcharge_percent: "0.00", open_advance_mode: "info_only" },
  "billing/allocation-basis-setting": { block_output: true },
  "billing/deadline-settings": { policy: "block_claims", watch_enabled: false, warn_days_first: 60, warn_days_second: 30 },
  "hoa/reserve-policy": { opening_lock_mode: "locked" },
  "hoa/reserve-payment-settings": { mode: "bound_only" },
  "hoa/plan-change-settings": { mode: "notice" },
  "hoa/acquisition-rules": {
    items: [
      { acquisition_kind: "purchase", variant: "manual_release", source_note: null },
      { acquisition_kind: "inheritance", variant: "manual_release", source_note: "Gutachten" },
      { acquisition_kind: "first_acquisition", variant: "manual_release", source_note: null },
      { acquisition_kind: "foreclosure", variant: "manual_release", source_note: null },
      { acquisition_kind: "gift", variant: "manual_release", source_note: null },
      { acquisition_kind: "other", variant: "manual_release", source_note: null },
    ],
  },
  "hoa/meeting-settings": {
    invitation_weeks: 3,
    virtual_meetings_enabled: false,
    virtual_basis_term_lock_enabled: false,
    virtual_basis_transition_date: "2026-12-31",
  },
  "hoa/online-meeting-settings": { enabled: false, proxy_conflict_mode: "flag" },
  "portal-admin/features": { owner_rental_income_enabled: false, owner_ticket_scope: "released", provider_rating_display: "off" },
  "tenant/legal-texts-config": { terms_version_mode: "manual" },
  "banking/automation/switch-requests": { enabled: false, g1_open: false, can_request: true, items: [] },
};

function row(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`row ${id} missing`);
  return el;
}

// The whole workspace shares the machine in wave 16: allow slow renders of the 40 rows.
vi.setConfig({ testTimeout: 30000 });

describe("BusinessRulesList", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows value, default, variants and the open question for each switch", () => {
    renderIntl(<BusinessRulesList initialDocs={DOCS} permissions={ALL} />);
    const r = within(row("rent-invoice-numbering"));
    expect(r.getByText("Entscheidung offen")).toBeInTheDocument();
    expect(r.getByTestId("current-rent-invoice-numbering")).toHaveTextContent("Entwurfsnummer ENTWURF-JJJJ-NNNNNN");
    expect(r.getByTestId("default-rent-invoice-numbering")).toHaveTextContent("Entwurfsnummer ENTWURF-JJJJ-NNNNNN");
    expect(r.getAllByText(/Reguläre Rechnungsnummer MR auch im Entwurf/).length).toBeGreaterThan(0);
    expect(r.getByText("AC03-01")).toBeInTheDocument();
    expect(r.getAllByText(/in docs\/OPEN_QUESTIONS\.md/).length).toBeGreaterThan(0);
    expect(r.getByRole("link", { name: "Fachmaske öffnen" })).toHaveAttribute("href", "/vertraege");
    // several questions use the plural label
    expect(within(row("period-lock-mode")).getByText("Offene Fragen")).toBeInTheDocument();
    expect(within(row("period-lock-mode")).getByText("P06-02, AA08-01")).toBeInTheDocument();
    // German date and numbers
    expect(within(row("virtual-basis-transition-date")).getByTestId("current-virtual-basis-transition-date")).toHaveTextContent("31.12.2026");
    expect(within(row("deadline-warn-first")).getByTestId("current-deadline-warn-first")).toHaveTextContent("60");
    expect(screen.getByTestId("rules-summary")).toHaveTextContent("Regeln, davon");
  });

  it("asks before leaving the default, then writes the variant and shows it as current", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ mode: "due_now" }));
    renderIntl(<BusinessRulesList initialDocs={DOCS} permissions={ALL} />);
    const r = within(row("plan-change-mode"));
    await userEvent.selectOptions(r.getByRole("combobox"), "due_now");
    await userEvent.click(r.getByRole("button", { name: "Speichern" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(r.getByRole("alertdialog")).toHaveTextContent("weicht vom Standard ab");
    await userEvent.click(r.getByRole("button", { name: "Änderung bestätigen" }));
    await waitFor(() => expect(r.getByRole("status")).toHaveTextContent("Gespeichert."));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/hoa/plan-change-settings");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ mode: "due_now" });
    expect(r.getByTestId("current-plan-change-mode")).toHaveTextContent("Differenz sofort fällig");
    expect(r.getByTestId("default-plan-change-mode")).toHaveTextContent("Nur Hinweis");
  });

  it("goes back to the default without a confirmation and cancels a pending change", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ mode: "notice" }));
    renderIntl(<BusinessRulesList initialDocs={{ ...DOCS, "hoa/plan-change-settings": { mode: "due_now" } }} permissions={ALL} />);
    const r = within(row("plan-change-mode"));
    await userEvent.selectOptions(r.getByRole("combobox"), "notice");
    await userEvent.click(r.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(r.queryByRole("alertdialog")).not.toBeInTheDocument();

    const p = within(row("reserve-payment-mode"));
    await userEvent.selectOptions(p.getByRole("combobox"), "plan_ratio_proposal");
    await userEvent.click(p.getByRole("button", { name: "Speichern" }));
    await userEvent.click(p.getByRole("button", { name: "Abbrechen" }));
    expect(p.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends the whole tax document for the subledger switch (known gap AE06)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<BusinessRulesList initialDocs={DOCS} permissions={ALL} />);
    const r = within(row("subledger-exclude-written-off"));
    await userEvent.selectOptions(r.getByRole("combobox"), "false");
    await userEvent.click(r.getByRole("button", { name: "Speichern" }));
    await userEvent.click(r.getByRole("button", { name: "Änderung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/accounting/tax/settings");
    expect(JSON.parse(String(init?.body))).toMatchObject({ construction_withholding_percent: "15.00", approval_limits: [], subledger_exclude_written_off: false });
  });

  it("writes the opening balance switch and one acquisition kind with its source note", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<BusinessRulesList initialDocs={DOCS} permissions={ALL} />);
    const o = within(row("opening-lock-mode"));
    await userEvent.selectOptions(o.getByRole("combobox"), "four_eyes");
    await userEvent.click(o.getByRole("button", { name: "Speichern" }));
    await userEvent.click(o.getByRole("button", { name: "Änderung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/hoa/reserve-policy");
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ opening_lock_mode: "four_eyes" });

    const a = within(row("acquisition-inheritance"));
    await userEvent.selectOptions(a.getByRole("combobox"), "by_resolution_date");
    await userEvent.click(a.getByRole("button", { name: "Speichern" }));
    await userEvent.click(a.getByRole("button", { name: "Änderung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1]![0])).toBe("/api/bff/hoa/acquisition-rules/inheritance");
    expect(JSON.parse(String(fetchMock.mock.calls[1]![1]?.body))).toEqual({ variant: "by_resolution_date", source_note: "Gutachten" });
  });

  it("writes a number and clears a date", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<BusinessRulesList initialDocs={DOCS} permissions={ALL} />);
    const w = within(row("deadline-warn-first"));
    const input = w.getByLabelText("Ändern");
    await userEvent.clear(input);
    await userEvent.type(input, "45");
    await userEvent.click(w.getByRole("button", { name: "Speichern" }));
    await userEvent.click(w.getByRole("button", { name: "Änderung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ warn_days_first: 45 });

    const d = within(row("virtual-basis-transition-date"));
    await userEvent.clear(d.getByLabelText("Ändern"));
    // clearing the date returns to the default (no date entered): no confirmation needed
    await userEvent.click(d.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1]![1]?.body))).toMatchObject({ invitation_weeks: 3, virtual_basis_transition_date: null });
  });

  it("shows the server error and keeps the old value", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Konflikt", detail: "Nicht erlaubt." }, 409));
    renderIntl(<BusinessRulesList initialDocs={DOCS} permissions={ALL} />);
    const r = within(row("advance-open-mode"));
    await userEvent.selectOptions(r.getByRole("combobox"), "offset_reversal");
    await userEvent.click(r.getByRole("button", { name: "Speichern" }));
    await userEvent.click(r.getByRole("button", { name: "Änderung bestätigen" }));
    await waitFor(() => expect(r.getByRole("alert")).toBeInTheDocument());
    expect(r.getByTestId("current-advance-open-mode")).toHaveTextContent("Nur Information");
  });

  it("shows display-only rules without a change control and links to the specialist screen", () => {
    renderIntl(<BusinessRulesList initialDocs={DOCS} permissions={ALL} />);
    const a = within(row("automation-switch"));
    expect(a.queryByRole("combobox")).not.toBeInTheDocument();
    expect(a.getByText(/Nur Anzeige/)).toBeInTheDocument();
    expect(a.getByTestId("current-automation-switch")).toHaveTextContent("Aus");
    expect(a.getByRole("link", { name: "Fachmaske öffnen" })).toHaveAttribute("href", "/einstellungen/buchhaltung/automatik");
    const l = within(row("interest-tax"));
    expect(l.getByTestId("default-interest-tax")).toHaveTextContent("Keine Steuerkonten");
    expect(within(row("rule-checkpoints")).getByTestId("current-rule-checkpoints")).toHaveTextContent("0 Einträge");
  });

  it("needs a reason for the four eyes switch of the chart and writes it to the newest version", async () => {
    const id = "33333333-3333-3333-3333-333333333333";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<BusinessRulesList initialDocs={{ ...DOCS, "accounting/templates": [{ id, version: 3, four_eyes_required: true }] }} permissions={ALL} />);
    const c = within(row("chart-four-eyes"));
    expect(c.getByTestId("current-chart-four-eyes")).toHaveTextContent("Ein");
    await userEvent.selectOptions(c.getByRole("combobox"), "false");
    expect(c.getByRole("button", { name: "Speichern" })).toBeDisabled();
    await userEvent.type(c.getByLabelText("Begründung"), "Einzelperson im Aufbau");
    await userEvent.click(c.getByRole("button", { name: "Speichern" }));
    await userEvent.click(c.getByRole("button", { name: "Änderung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/bff/accounting/templates/${id}/four-eyes`);
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ required: false, reason: "Einzelperson im Aufbau" });
    expect(c.getByTestId("current-chart-four-eyes")).toHaveTextContent("Aus");
  });

  it("asks for a justification of ten characters when the legal basis leaves consent", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    const docs = { ...DOCS, "consent-legal-basis": { items: [{ purpose: "marketing", basis: "consent", note: null }] } };
    renderIntl(<BusinessRulesList initialDocs={docs} permissions={[...ALL, "contacts:read"]} />);
    const m = within(row("legal-basis-marketing"));
    expect(m.queryByLabelText("Begründung")).not.toBeInTheDocument();
    await userEvent.selectOptions(m.getByRole("combobox"), "legitimate_interest");
    await userEvent.type(m.getByLabelText("Begründung"), "zu kurz");
    expect(m.getByRole("button", { name: "Speichern" })).toBeDisabled();
    await userEvent.type(m.getByLabelText("Begründung"), " und nun lang genug");
    await userEvent.click(m.getByRole("button", { name: "Speichern" }));
    await userEvent.click(m.getByRole("button", { name: "Änderung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/consent-legal-basis/marketing");
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({
      basis: "legitimate_interest",
      note: "zu kurz und nun lang genug",
    });
  });

  it("resets a legal basis to the default through DELETE (AF19)", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ items: [] }));
    const docs = { ...DOCS, "consent-legal-basis": { items: [{ purpose: "marketing", basis: "legitimate_interest", note: "Bestandskunden und Begründung" }] } };
    renderIntl(<BusinessRulesList initialDocs={docs} permissions={[...ALL, "contacts:read", "contacts:approve"]} />);
    const m = within(row("legal-basis-marketing"));
    await userEvent.click(m.getByRole("button", { name: "Auf Standard zurücksetzen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/consent-legal-basis/marketing");
    expect(fetchMock.mock.calls[0]![1]?.method).toBe("DELETE");
    await waitFor(() => expect(m.getByTestId("current-legal-basis-marketing")).toHaveTextContent(/Einwilligung/));
  });

  it("hides rules without the read permission and blocks the change without the write permission", () => {
    renderIntl(<BusinessRulesList initialDocs={DOCS} permissions={["tenant_settings:read"]} />);
    expect(document.getElementById("period-lock-mode")).toBeNull();
    const r = within(row("opening-lock-mode"));
    expect(r.queryByRole("combobox")).not.toBeInTheDocument();
    expect(r.getByText("Ihnen fehlt das Recht zum Ändern.")).toBeInTheDocument();
    expect(r.getByTestId("current-opening-lock-mode")).toHaveTextContent("Gesperrt");
  });

  it("marks an unreadable endpoint and offers no change", () => {
    renderIntl(<BusinessRulesList initialDocs={{ ...DOCS, "billing/advance-rule": null }} permissions={ALL} />);
    const r = within(row("advance-open-mode"));
    expect(r.getByTestId("current-advance-open-mode")).toHaveTextContent("nicht lesbar");
    expect(r.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
