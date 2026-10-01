import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvitationForm } from "./InvitationForm";
import { TermsAcceptForm } from "./TermsAcceptForm";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh, back: vi.fn() }) }));

describe("terms acceptance (AC06)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("needs the checkbox and sends accept_terms with the published version", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ terms_version: "2026-10", accepted: true }));
    renderIntl(<TermsAcceptForm version="2026-10" next="/dokumente" />);
    expect(screen.getByText("Fassung: 2026-10")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Annehmen und fortfahren" }));
    expect(screen.getByRole("alert").textContent).toContain("Annahme der Nutzungsbedingungen");
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Annehmen und fortfahren" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dokumente"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/portal/terms/accept");
    expect(JSON.parse(String(init?.body))).toEqual({ accept_terms: true, terms_version: "2026-10" });
  });

  it("shows the API error and stays on the page", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ title: "Nutzungsbedingungen fehlen", detail: "Fassung abweichend.", code: "MHVP-CONT-0020" }, 409),
    );
    renderIntl(<TermsAcceptForm version="2026-10" />);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Annehmen und fortfahren" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(push).not.toHaveBeenCalled();
  });

  it("activation asks for the terms after MHVP-CONT-0020 and resends with the version", async () => {
    fetchMock
      .mockImplementationOnce(async () =>
        jsonResponse(
          { title: "Nutzungsbedingungen fehlen", detail: "Bitte die Nutzungsbedingungen in der Fassung 2026-10 annehmen.", code: "MHVP-CONT-0020" },
          403,
        ),
      )
      .mockImplementationOnce(async () => jsonResponse({ status: "active" }));
    renderIntl(<InvitationForm code="ABCDEFGHIJKL" />);
    await userEvent.type(screen.getByLabelText("Neues Passwort"), "ein-langes-passwort");
    await userEvent.type(screen.getByLabelText("Passwort wiederholen"), "ein-langes-passwort");
    await userEvent.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    const box = await screen.findByRole("checkbox");
    await userEvent.click(box);
    await userEvent.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1]![1]?.body))).toMatchObject({
      accept_terms: true,
      terms_version: "2026-10",
    });
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).not.toHaveProperty("accept_terms");
  });
});
