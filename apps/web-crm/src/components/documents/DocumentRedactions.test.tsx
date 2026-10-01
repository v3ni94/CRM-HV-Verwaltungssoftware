import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DocumentRedactions, type Redaction } from "./DocumentRedactions";

const DOC = "01920000-0000-7000-8000-00000000d0c1";
const COPY = "01920000-0000-7000-8000-00000000d0c2";
const RID = "01920000-0000-7000-8000-00000000ed01";

const pending: Redaction = {
  id: RID,
  original_document_id: DOC,
  copy_document_id: COPY,
  reason: "Daten Dritter",
  scope: "Seite 2, Namen",
  steps: ["Namen geschwärzt"],
  created_by: "u-creator",
  created_at: "2026-09-30T10:00:00Z",
  released_at: null,
  released_by: null,
  released_visibility: null,
};

describe("DocumentRedactions", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("lists copies and blocks the release by the creator (four eyes)", () => {
    renderIntl(<DocumentRedactions documentId={DOC} initial={[pending]} userId="u-creator" canCreate canApprove />);
    expect(screen.getByText("wartet auf Freigabe", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Die Freigabe erteilt eine zweite Person.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Freigeben" })).toBeNull();
    expect(screen.getByRole("link", { name: "Kopie öffnen" })).toHaveAttribute("href", `/dokumente/${COPY}`);
  });

  it("releases with the chosen visibility as a second person", async () => {
    const user = userEvent.setup();
    const released = { ...pending, released_at: "2026-09-30T11:00:00Z", released_by: "u-second", released_visibility: ["owner"] };
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/release")) return jsonResponse(released);
      return jsonResponse([released]);
    });
    renderIntl(<DocumentRedactions documentId={DOC} initial={[pending]} userId="u-second" canCreate={false} canApprove />);
    await user.click(screen.getByRole("button", { name: "Freigeben" }));
    await user.click(screen.getByRole("button", { name: "Jetzt freigeben" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mindestens eine Sichtbarkeit");
    await user.click(screen.getByLabelText("Eigentümer"));
    await user.click(screen.getByRole("button", { name: "Jetzt freigeben" }));
    await waitFor(() => expect(screen.getByText("Die Kopie wurde freigegeben.")).toBeInTheDocument());
    const call = fetchMock.mock.calls[0];
    expect(String(call?.[0])).toBe(`/api/bff/documents/${DOC}/redactions/${RID}/release`);
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ visibility: ["owner"] });
  });

  it("creates a copy with reason, scope and steps and validates input", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input, init) => {
      if ((init as RequestInit | undefined)?.method === "POST") return jsonResponse(pending, 201);
      return jsonResponse([pending]);
    });
    renderIntl(<DocumentRedactions documentId={DOC} initial={[]} userId="u1" canCreate canApprove={false} />);
    expect(screen.getByText("Keine geschwärzten Kopien vorhanden.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kopie anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Datei, Grund");
    await user.upload(screen.getByLabelText("Geschwärzte Datei"), new File(["%PDF-1.4"], "g.pdf", { type: "application/pdf" }));
    await user.type(screen.getByLabelText("Grund"), "Daten Dritter");
    await user.type(screen.getByLabelText("Umfang der Schwärzung"), "Seite 2");
    await user.type(screen.getByLabelText("Bearbeitungsschritte"), "Namen geschwärzt{enter}Geprüft");
    await user.click(screen.getByRole("button", { name: "Kopie anlegen" }));
    await waitFor(() => expect(screen.getAllByTestId("redaction-item")).toHaveLength(1));
    const body = (fetchMock.mock.calls[0]?.[1] as RequestInit).body as FormData;
    expect(JSON.parse(String(body.get("steps")))).toEqual(["Namen geschwärzt", "Geprüft"]);
    expect(body.get("reason")).toBe("Daten Dritter");
  });
});
