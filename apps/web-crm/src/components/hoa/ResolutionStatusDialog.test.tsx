import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ResolutionStatusDialog } from "./ResolutionStatusDialog";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const RID = "0192abcd-0000-7000-8000-000000000040";

describe("ResolutionStatusDialog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requires a reason and patches status and court note without cancelling anything", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: RID, status: "contested" }));
    renderIntl(<ResolutionStatusDialog resolutionId={RID} currentNotes="Altvermerk" />);
    await userEvent.click(screen.getByText("Status ändern"));
    expect(screen.getByText(/storniert nichts automatisch/)).toBeInTheDocument();
    const save = screen.getByText("Status speichern");
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Gericht"), "AG Musterstadt");
    await userEvent.type(screen.getByLabelText("Aktenzeichen"), "12 C 34/26");
    await userEvent.type(screen.getByLabelText("Begründung (Pflicht)"), "Anfechtungsklage eingegangen");
    await userEvent.click(save);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/resolutions/${RID}`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body.status).toBe("contested");
    expect(body.court_notes).toContain("Altvermerk");
    expect(body.court_notes).toContain("AG Musterstadt");
    expect(body.court_notes).toContain("12 C 34/26");
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the refusal of the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung hoa:write." }, 403));
    renderIntl(<ResolutionStatusDialog resolutionId={RID} />);
    await userEvent.click(screen.getByText("Status ändern"));
    await userEvent.selectOptions(screen.getByLabelText("Neuer Status"), "annulled");
    await userEvent.type(screen.getByLabelText("Begründung (Pflicht)"), "Urteil liegt vor");
    await userEvent.click(screen.getByText("Status speichern"));
    expect(await screen.findByRole("alert")).toHaveTextContent("hoa:write");
  });
});
