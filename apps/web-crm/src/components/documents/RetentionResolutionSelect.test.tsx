import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RetentionResolutionSelect } from "./RetentionResolutionSelect";

const DOC = "01920000-0000-7000-8000-00000000000d";
const ENTITY = "01920000-0000-7000-8000-0000000000e1";

describe("RetentionResolutionSelect", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("loads the resolutions of the entity and saves the chosen one on the document", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([{ id: "res-1", number: 3, decided_on: "2026-05-04", subject: "Dachsanierung", status: "positive" }]),
    );
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: DOC }));
    renderIntl(<RetentionResolutionSelect documentId={DOC} legalEntityId={ENTITY} current={null} />);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/resolutions?legal_entity_id=${ENTITY}`);
    const option = await screen.findByText("Nr. 3 vom 04.05.2026: Dachsanierung");
    expect(screen.getByText("Beschluss speichern")).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Beschluss für den Fristbeginn"), option);
    await userEvent.click(screen.getByText("Beschluss speichern"));
    await waitFor(() => expect(screen.getByText("Beschluss gespeichert.")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(`/api/bff/documents/${DOC}`);
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({ retention_resolution_id: "res-1" });
  });
});
