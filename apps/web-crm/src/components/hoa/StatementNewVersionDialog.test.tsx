import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { StatementNewVersionDialog } from "./StatementNewVersionDialog";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

const ST = "01920000-0000-7000-8000-0000000004a1";
const ENTITY = "01920000-0000-7000-8000-0000000004e1";

describe("StatementNewVersionDialog (GAH-402)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("sends reason, basis and correcting resolution and shows the majority check", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([{ id: "res-1", number: 4, subject: "Korrektur 2025", decided_on: "2026-05-10" }]),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "st-2",
        version: 2,
        correction_majority_check: { result: "erreicht", rule_text: "Einfache Mehrheit nach Köpfen", standard_rule: true },
      }),
    );
    renderIntl(<StatementNewVersionDialog statementId={ST} legalEntityId={ENTITY} />);
    await userEvent.click(screen.getByText("Neue Version"));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/resolutions?legal_entity_id=${ENTITY}`);
    const option = await screen.findByText("4 Korrektur 2025 (10.05.2026)");
    await userEvent.selectOptions(screen.getByLabelText("Korrekturgrund"), "calculation_error");
    await userEvent.type(screen.getByLabelText("Grundlage (Beschreibung)"), "Umlage falsch");
    await userEvent.selectOptions(screen.getByLabelText("Korrekturbeschluss"), option);
    await userEvent.click(screen.getByText("Neue Version anlegen"));
    await waitFor(() => expect(screen.getByText("Version 2 angelegt.")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(`/api/bff/hoa/statements/${ST}/new-version`);
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      reason: "calculation_error",
      basis: "Umlage falsch",
      resolution_id: "res-1",
    });
    expect(screen.getByTestId("majority-check")).toHaveTextContent("Einfache Mehrheit nach Köpfen");
  });

  it("sends an empty body without inputs and shows the API error (foreign GdWE 422)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ code: "MHVP-HOA-0038", title: "Korrekturbeschluss gehört zu einer anderen GdWE", status: 422 }, 422),
    );
    renderIntl(<StatementNewVersionDialog statementId={ST} legalEntityId={ENTITY} />);
    await userEvent.click(screen.getByText("Neue Version"));
    await userEvent.click(screen.getByText("Neue Version anlegen"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({});
    expect(screen.queryByTestId("majority-check")).toBeNull();
  });
});
