import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

import { MajorityRulesAdmin, type SubjectRule } from "./MajorityRulesAdmin";

const rule: SubjectRule = {
  id: "r1",
  legal_entity_id: null,
  subject_kind: "structural_change",
  majority_type: "qualified_2_3",
  custom_numerator: null,
  custom_denominator: null,
  counting_basis: "shares",
  source: "Gemeinschaftsordnung § 7, zu prüfen",
  approved_by: null,
  rule_text: "",
};

describe("MajorityRulesAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists rules with scope, type, basis and release state", () => {
    renderIntl(<MajorityRulesAdmin rules={[rule]} entities={[]} canManage={false} />);
    expect(screen.getAllByText("Bauliche Veränderung").length).toBeGreaterThan(0);
    expect(screen.getByText("qualifiziert 2/3")).toBeInTheDocument();
    expect(screen.getByText("Miteigentumsanteile")).toBeInTheDocument();
    expect(screen.getByText("nicht freigegeben")).toBeInTheDocument();
    expect(screen.queryByText("Regel anlegen")).not.toBeInTheDocument();
  });

  it("creates a custom rule with source", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(rule, 201));
    renderIntl(<MajorityRulesAdmin rules={[]} entities={[{ id: "le1", name: "WEG Musterstraße" }]} canManage={true} />);
    await userEvent.selectOptions(screen.getByLabelText("Mehrheit"), "custom");
    await userEvent.type(screen.getByLabelText("Zähler"), "3");
    await userEvent.type(screen.getByLabelText("Nenner"), "5");
    await userEvent.selectOptions(screen.getByLabelText("Geltung"), "le1");
    await userEvent.type(screen.getByLabelText("Fundstelle"), "Vereinbarung 2019, zu prüfen");
    await userEvent.click(screen.getByText("Regel anlegen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/hoa/majority-rules/subject-rules");
    expect(JSON.parse(String(init.body))).toMatchObject({
      legal_entity_id: "le1",
      majority_type: "custom",
      custom_numerator: 3,
      custom_denominator: 5,
      source: "Vereinbarung 2019, zu prüfen",
    });
  });
});

describe("MajorityRulesAdmin usability (review 26.09.2026)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("explains why the form cannot be sent and blocks an invalid custom fraction", async () => {
    renderIntl(<MajorityRulesAdmin rules={[]} entities={[]} canManage={true} />);
    expect(screen.getByText("Fundstelle mit mindestens 3 Zeichen angeben.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Fundstelle"), "GO § 7");
    await userEvent.selectOptions(screen.getByLabelText("Mehrheit"), "custom");
    await userEvent.type(screen.getByLabelText("Zähler"), "5");
    await userEvent.type(screen.getByLabelText("Nenner"), "3");
    expect(screen.getByText(/Zähler und Nenner als ganze Zahlen/)).toBeInTheDocument();
    expect(screen.getByText("Regel anlegen")).toBeDisabled();
  });

  it("confirms a saved rule", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(rule, 201));
    renderIntl(<MajorityRulesAdmin rules={[]} entities={[]} canManage={true} />);
    await userEvent.type(screen.getByLabelText("Fundstelle"), "Gemeinschaftsordnung § 7");
    await userEvent.click(screen.getByText("Regel anlegen"));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Gespeichert."));
  });
});
