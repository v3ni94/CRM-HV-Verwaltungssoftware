import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HoaCreate, HoaItemForm, HoaSteps, MajorityRules, MeetingPanel, PlanApplyPreview } from "./HoaForms";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const ST = "0192abcd-0000-7000-8000-000000000020";
const LE = "0192abcd-0000-7000-8000-000000000021";
const RES = "0192abcd-0000-7000-8000-000000000022";

describe("HoaSteps", () => {
  afterEach(() => vi.restoreAllMocks());

  it("records the resolution bound to the snapshot hash, then moves to resolved", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ id: RES, number: 1, status: "positive" }, 201))
      .mockResolvedValueOnce(jsonResponse({ status: "resolved" }));
    renderIntl(<HoaSteps target="statement" id={ST} status="internally_approved" legalEntityId={LE} snapshotHash={"a".repeat(64)} />);
    await userEvent.type(screen.getByLabelText("Beschlussdatum"), "2026-05-10");
    await userEvent.click(screen.getByText("Beschluss zu diesem Stand erfassen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const first = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(first).toMatchObject({ legal_entity_id: LE, subject_type: "hoa_statement", subject_id: ST, snapshot_hash: "a".repeat(64) });
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain(`/statements/${ST}/transition`);
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ target: "resolved", resolution_id: RES });
  });

  it("locks issue, due and post behind G4 while the gate is closed (GAM-101)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([{ gate: "G4", label: "G4", open: false, scopes: [] }]));
    renderIntl(<HoaSteps target="statement" id={ST} status="due" legalEntityId={LE} snapshotHash={null} />);
    expect(await screen.findByText(/Gesperrt, solange die Freigabestufe G4/)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Ergebnis buchen" });
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("posts after confirmation when G4 is open and shows an API refusal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).endsWith("/tenant/release-gates")
        ? jsonResponse([{ gate: "G4", label: "G4", open: true, scopes: [] }])
        : jsonResponse({ title: "Vier-Augen", status: 403, detail: "Zweite Person erforderlich." }, 403),
    );
    renderIntl(<HoaSteps target="statement" id={ST} status="due" legalEntityId={LE} snapshotHash={null} />);
    const button = screen.getByRole("button", { name: "Ergebnis buchen" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("Zweite Person");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain(`/statements/${ST}/post`);
  });

  it("issues with the target body when G4 is open", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).endsWith("/tenant/release-gates") ? jsonResponse([{ gate: "G4", label: "G4", open: true, scopes: [] }]) : jsonResponse({ status: "issued" }),
    );
    renderIntl(<HoaSteps target="statement" id={ST} status="resolved" legalEntityId={LE} snapshotHash={null} />);
    const button = screen.getByRole("button", { name: "Ausgeben" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ target: "issued" });
    expect(refresh).toHaveBeenCalled();
  });

  it("offers existing resolutions of the subject and transitions with the chosen id (GAM-102)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ status: "resolved" }));
    const hash = "a".repeat(64);
    const resolutions = [
      { id: RES, number: 7, decided_on: "2026-05-10", subject: "Jahresabrechnung 2025", status: "positive", subject_type: "hoa_statement", subject_id: ST, snapshot_hash: hash },
      { id: "r-other", number: 8, decided_on: "2026-05-10", subject: "Fremder Stand", status: "positive", subject_type: "hoa_statement", subject_id: ST, snapshot_hash: "c".repeat(64) },
      { id: "r-neg", number: 9, decided_on: "2026-05-10", subject: "Abgelehnt", status: "negative" },
    ];
    renderIntl(<HoaSteps target="statement" id={ST} status="internally_approved" legalEntityId={LE} snapshotHash={hash} resolutions={resolutions} />);
    const select = screen.getByLabelText("Bestehenden Beschluss verwenden");
    expect(screen.getAllByRole("option")).toHaveLength(2);
    expect(screen.queryByText(/Fremder Stand/)).toBeNull();
    await userEvent.selectOptions(select, RES);
    await userEvent.click(screen.getByTestId("resolution-use-existing"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(`/statements/${ST}/transition`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ target: "resolved", resolution_id: RES });
  });
});

describe("PlanApplyPreview", () => {
  afterEach(() => vi.restoreAllMocks());
  const PLAN = "0192abcd-0000-7000-8000-000000000030";
  const preview = {
    valid_from: "2027-01-01",
    snapshot_hash: "b".repeat(64),
    applied_at: null,
    can_apply: true,
    rows: [
      { unit_number: "01", component: "hoa_fee", owner: "Eigentümer 01", contract_number: "E-1", current: "250.00", new: "300.00", action: "create", rhythm: "quarterly", instalment: "900.00" },
      { unit_number: "02", component: "reserve", owner: null, contract_number: null, current: null, new: "40.00", action: "no_contract" },
    ],
    counts: { create: 1, unchanged: 0, zero: 0, no_contract: 1 },
    posted_months: 2,
  };

  it("loads the preview and applies with confirmation and the snapshot hash", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(preview))
      .mockResolvedValueOnce(jsonResponse({ payments_created: 1, applied_at: "2026-09-29T10:00:00Z" }));
    renderIntl(<HoaSteps target="plan" id={PLAN} status="resolved" legalEntityId={LE} snapshotHash={"b".repeat(64)} />);
    await userEvent.click(screen.getByTestId("plan-apply-load"));
    expect(await screen.findByTestId("plan-apply-row-01-hoa_fee")).toHaveTextContent("300,00 EUR");
    expect(screen.getByTestId("plan-apply-row-01-hoa_fee")).toHaveTextContent("anlegen");
    expect(screen.getByTestId("plan-apply-instalment-01-hoa_fee")).toHaveTextContent("vierteljährlich: 900,00 EUR");
    expect(screen.getByTestId("plan-apply-row-02-reserve")).toHaveTextContent("kein Eigentumsverhältnis");
    expect(screen.getByText("1 anlegen, 0 unverändert, 1 ohne Eigentumsverhältnis")).toBeInTheDocument();
    expect(screen.getByText(/Bereits gebuchte Monate ab Wirksamkeitsbeginn: 2/)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("plan-apply-confirm"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(`/api/bff/hoa/plans/${PLAN}/apply`);
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ confirm: true, snapshot_hash: "b".repeat(64) });
    expect(await screen.findByText("Übernommen: 1 Sollbeträge angelegt.")).toBeInTheDocument();
  });

  it("shows the four eyes refusal of the API", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(preview))
      .mockResolvedValueOnce(jsonResponse({ title: "Freigabe durch eine zweite Person erforderlich", status: 403, detail: "Die Übernahme muss eine andere Person als der Ersteller bestätigen." }, 403));
    renderIntl(<PlanApplyPreview id={PLAN} snapshotHash={null} />);
    await userEvent.click(screen.getByTestId("plan-apply-load"));
    await userEvent.click(await screen.findByTestId("plan-apply-confirm"));
    expect(await screen.findByRole("alert")).toHaveTextContent("andere Person");
  });
});

describe("MeetingPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("tallies and announces the proposed outcome with the majority basis", async () => {
    const item = "0192abcd-0000-7000-8000-000000000023";
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ yes: "700", no: "300", abstain: "0", proposal: "positive", manual_check: false }))
      .mockResolvedValueOnce(jsonResponse({ id: "r", number: 1, status: "positive" }, 201));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<MeetingPanel id="m" status="held" agenda={[{ id: item, position: 1, title: "Dach", majority: "simple", resolution: null }]} />);
    await userEvent.click(screen.getByText("Auszählen"));
    expect(await screen.findByTestId(`tally-${item}`)).toHaveTextContent("Ja 700 · Nein 300");
    await userEvent.click(screen.getByText("Verkünden: angenommen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({
      outcome: "positive",
      majority_basis: "Einfache Mehrheit der abgegebenen Stimmen",
    });
  });
});

describe("MajorityRules", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends shares as exact ratios with the source", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "r1" }, 201));
    renderIntl(<MajorityRules legalEntityId={LE} rules={[]} />);
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Doppelt qualifiziert");
    await userEvent.type(screen.getByLabelText("Anteil der abgegebenen Stimmen in %"), "66,67");
    await userEvent.type(screen.getByLabelText("Mindestanteil aller MEA in %"), "50");
    await userEvent.type(screen.getByLabelText("Fundstelle (Gesetz, Vereinbarung)"), "Gemeinschaftsordnung § 5");
    await userEvent.type(screen.getByLabelText("Gültig ab"), "2020-01-01");
    await userEvent.click(screen.getByText("Regel anlegen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({
      legal_entity_id: LE,
      principle: "head",
      share_of_votes_cast: "0.6667",
      strictly_greater: true,
      min_mea_share_of_all: "0.5",
      unanimous: false,
      source: "Gemeinschaftsordnung § 5",
    });
  });

  it("describes existing rules", () => {
    renderIntl(
      <MajorityRules
        legalEntityId={LE}
        rules={[
          {
            id: "r1",
            label: "Bauliche Veränderung",
            principle: "mea",
            share_of_votes_cast: "0.66670000",
            strictly_greater: true,
            min_mea_share_of_all: "0.50000000",
            unanimous: false,
            source: "Testfundstelle",
            valid_from: "2020-01-01",
            valid_to: null,
          },
        ]}
      />,
    );
    expect(screen.getByText(/mehr als 66,67 %, mindestens 50 % aller MEA/)).toBeInTheDocument();
  });

  it("offers the four eyes approval only for draft rules (AN06)", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "r2" }));
    const base = {
      principle: "head",
      share_of_votes_cast: "0.5",
      strictly_greater: true,
      min_mea_share_of_all: null,
      unanimous: false,
      source: "Testfundstelle",
      valid_from: "2020-01-01",
      valid_to: null,
    };
    renderIntl(
      <MajorityRules
        legalEntityId={LE}
        rules={[
          { ...base, id: "r1", label: "Alt", approval_status: "approved" },
          { ...base, id: "r2", label: "Neu", approval_status: "draft" },
        ]}
      />,
    );
    expect(screen.queryByTestId("rule-draft-r1")).toBeNull();
    expect(screen.getByTestId("rule-draft-r2")).toHaveTextContent("Entwurf");
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/bff/hoa/majority-rules/r2/approve");
  });
});

describe("HoaCreate meeting", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requires the original meeting for a repeat and sends origin_meeting_id (GA03-01)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: RES }, 201));
    const { container } = renderIntl(
      <HoaCreate kind="meeting" legalEntityId={LE} basePath="/weg/x" originMeetings={[{ id: ST, label: "10.12.2026 14:00 · eingeladen" }]} />,
    );
    await userEvent.type(container.querySelector('input[type="datetime-local"]') as HTMLInputElement, "2026-12-10T14:00");
    await userEvent.selectOptions(screen.getByTestId("meeting-kind-select"), "repeat");
    await userEvent.click(screen.getByRole("button", { name: /Versammlung/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ursprungsversammlung");
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.selectOptions(screen.getByTestId("meeting-origin-select"), ST);
    await userEvent.click(screen.getByRole("button", { name: /Versammlung/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({ kind: "repeat", origin_meeting_id: ST, legal_entity_id: LE });
  });
});

describe("HoaItemForm sub community (AP21, GAM-109)", () => {
  afterEach(() => vi.restoreAllMocks());
  const KEYS = [{ id: "k1", code: "MEA", name: "Miteigentumsanteil" }];

  it("sends the chosen sub community with the cost position and shows the basis hint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "c1" }, 201));
    renderIntl(<HoaItemForm target="statement" id={ST} keys={KEYS} subCommunities={[{ id: "s1", code: "H1", name: "Haus 1" }]} />);
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Aufzug");
    await userEvent.type(screen.getByLabelText("Betrag"), "1000");
    await userEvent.type(screen.getByLabelText("Grundlage"), "Beschluss 4");
    await userEvent.selectOptions(screen.getByLabelText("Untergemeinschaft"), "s1");
    expect(screen.getByText(/Beschluss oder Dokument als Grundlage hinterlegen/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Position hinzufügen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({ sub_community_id: "s1", basis: "Beschluss 4" });
  });

  it("offers no sub community field without sub communities", () => {
    renderIntl(<HoaItemForm target="statement" id={ST} keys={KEYS} />);
    expect(screen.queryByLabelText("Untergemeinschaft")).toBeNull();
  });
});
