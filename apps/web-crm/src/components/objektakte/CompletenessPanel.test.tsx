import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CompletenessPanel } from "./CompletenessPanel";

vi.mock("@/components/documents/LetterRecordForm", () => ({
  LetterRecordForm: (props: { path: string; canCreate: boolean }) => (
    <div data-testid="letter-form" data-path={props.path} data-can-create={String(props.canCreate)} />
  ),
}));

const PROPERTY = "0192abcd-0000-7000-8000-000000000091";
const missing = [{ document_category_id: "c1", code: "TA", name: "Teilungserklärung" }];
const satisfied = [
  { document_category_id: "c2", code: "EA", name: "Energieausweis" },
  { document_category_id: "c3", code: "GB", name: "Grundbuchauszug" },
];

describe("CompletenessPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the API error as alert", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Kein Zugriff", status: 403 }, 403));
    renderIntl(<CompletenessPanel propertyId={PROPERTY} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("states completeness without action buttons", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ property_id: PROPERTY, management_type: "weg", missing: [], satisfied }),
    );
    renderIntl(<CompletenessPanel propertyId={PROPERTY} />);
    expect(await screen.findByText("Alle Pflichtunterlagen sind vorhanden.")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/bff/objektakte/properties/${PROPERTY}/completeness`);
    expect(screen.getByText("2 Pflichtunterlagen vorhanden")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("lists missing documents and shows the unsent draft after the request", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ property_id: PROPERTY, management_type: "weg", missing, satisfied: [] }))
      .mockResolvedValueOnce(jsonResponse({ draft: true, text: "Bitte reichen Sie die Teilungserklärung nach." }));
    renderIntl(<CompletenessPanel propertyId={PROPERTY} />);
    expect(await screen.findByText("Teilungserklärung")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Nachforderungsschreiben als Entwurf erzeugen" }));
    expect(await screen.findByText("Bitte reichen Sie die Teilungserklärung nach.")).toBeInTheDocument();
    expect(screen.getByText("Entwurf (nicht versendet)")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/objektakte/properties/${PROPERTY}/completeness/nachforderungsschreiben`);
    expect(init.method).toBe("POST");
  });

  it("toggles the letter form and passes the create permission on", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ property_id: PROPERTY, management_type: "weg", missing, satisfied: [] }));
    renderIntl(<CompletenessPanel propertyId={PROPERTY} canCreateLetter />);
    await screen.findByText("Teilungserklärung");
    expect(screen.queryByTestId("letter-form")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("completeness-letter-toggle"));
    const form = screen.getByTestId("letter-form");
    expect(form).toHaveAttribute("data-can-create", "true");
    expect(form).toHaveAttribute("data-path", `objektakte/properties/${PROPERTY}/completeness/nachforderungsschreiben/pdf`);
    await userEvent.click(screen.getByTestId("completeness-letter-toggle"));
    expect(screen.queryByTestId("letter-form")).not.toBeInTheDocument();
  });
});
