import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HoaSteps, MajorityRules, MeetingPanel } from "./HoaForms";

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

  it("shows the G4 refusal on posting", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ title: "Freigabestufe", status: 403, detail: "Freigabestufe G4 ist nicht erteilt." }, 403),
    );
    renderIntl(<HoaSteps target="statement" id={ST} status="due" legalEntityId={LE} snapshotHash={null} />);
    await userEvent.click(screen.getByText("Ergebnis buchen"));
    expect(await screen.findByRole("alert")).toHaveTextContent("G4");
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
});
