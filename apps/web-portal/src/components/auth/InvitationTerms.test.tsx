import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvitationForm } from "./InvitationForm";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), back: vi.fn() }) }));

const TENANT = "0123456789abcdef0123456789abcdef";
const CODE = `${TENANT}.geheimergeheimer`;

describe("invitation shows the published terms before activation (AD03-01, AE34)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("reads the version with the tenant id of the code and sends the acceptance with the first attempt", async () => {
    fetchMock.mockImplementation(async (input) =>
      String(input).startsWith("/api/session/terms")
        ? jsonResponse({ terms_version: "2026-10" })
        : jsonResponse({ status: "active" }),
    );
    renderIntl(<InvitationForm code={CODE} />);
    const box = await screen.findByRole("checkbox");
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/session/terms?tenant=${TENANT}`);
    expect(screen.getByText(/pseudonymisierte Kennung/)).toBeTruthy();
    await userEvent.click(screen.getByLabelText("Neues Passwort"));
    await userEvent.paste("ein-langes-passwort");
    await userEvent.click(screen.getByLabelText("Passwort wiederholen"));
    await userEvent.paste("ein-langes-passwort");
    await userEvent.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    expect(screen.getByRole("alert").textContent).toContain("Annahme der Nutzungsbedingungen");
    await userEvent.click(box);
    await userEvent.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1]![0])).toBe("/api/session/invitation");
    expect(JSON.parse(String(fetchMock.mock.calls[1]![1]?.body))).toMatchObject({
      accept_terms: true,
      terms_version: "2026-10",
    });
  });

  it("shows no checkbox when the tenant publishes no terms (404) and does not ask for a code without tenant id", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ title: "Nicht gefunden" }, 404));
    renderIntl(<InvitationForm code={CODE} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("does not call the public endpoint for a code without tenant id", async () => {
    renderIntl(<InvitationForm code="ABCDEFGHIJKL" />);
    await userEvent.type(screen.getByLabelText("Neues Passwort"), "x");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
