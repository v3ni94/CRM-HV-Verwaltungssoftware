import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OidcClientsAdmin } from "./OidcClientsAdmin";

const client = { client_id: "status", name: "Statusseite", redirect_uris: ["https://s.example.org/cb"], public: false, active: true };
const publicClient = { ...client, client_id: "spa", name: "Webtool", public: true };

describe("OidcClientsAdmin", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const findCall = (method: string, part: string) =>
    fetchMock.mock.calls.find((c) => ((c[1] as RequestInit | undefined)?.method ?? "GET") === method && String(c[0]).includes(part)) as [string, RequestInit] | undefined;

  it("lists clients and offers no secret rotation for public clients", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([client, publicClient]));
    renderIntl(<OidcClientsAdmin />);
    expect(await screen.findByText("Statusseite")).toBeInTheDocument();
    const publicRow = screen.getByText("Webtool").closest("tr") as HTMLElement;
    expect(within(publicRow).queryByRole("button", { name: "Secret erneuern" })).toBeNull();
    const row = screen.getByText("Statusseite").closest("tr") as HTMLElement;
    expect(within(row).getByRole("button", { name: "Secret erneuern" })).toBeInTheDocument();
  });

  it("creates a client with trimmed redirect URIs and shows the secret once", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<OidcClientsAdmin />);
    await screen.findByText("Keine Clients angelegt.");
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ...client, client_secret: "geheim-123" }, 201))
      .mockResolvedValueOnce(jsonResponse([client]));
    await userEvent.type(screen.getByLabelText("Client-ID"), " status ");
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Statusseite");
    await userEvent.type(screen.getByLabelText(/Redirect-URIs/), "https://s.example.org/cb{enter}  {enter}https://t.example.org/cb");
    await userEvent.click(screen.getByRole("button", { name: "Client anlegen" }));
    expect(await screen.findByText("geheim-123")).toBeInTheDocument();
    const post = findCall("POST", "/platform/oidc-clients") as [string, RequestInit];
    expect(JSON.parse(String(post[1].body))).toEqual({
      client_id: "status",
      name: "Statusseite",
      redirect_uris: ["https://s.example.org/cb", "https://t.example.org/cb"],
      public: false,
    });
    expect(await screen.findByText("Statusseite")).toBeInTheDocument();
  });

  it("shows the problem message when the client exists", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<OidcClientsAdmin />);
    await screen.findByText("Keine Clients angelegt.");
    fetchMock.mockResolvedValueOnce(jsonResponse({ title: "Konflikt", detail: "OIDC client already exists", status: 409 }, 409));
    await userEvent.type(screen.getByLabelText("Client-ID"), "status");
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Statusseite");
    await userEvent.type(screen.getByLabelText(/Redirect-URIs/), "https://s.example.org/cb");
    await userEvent.click(screen.getByRole("button", { name: "Client anlegen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("rotates the secret only after confirmation", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([client]));
    renderIntl(<OidcClientsAdmin />);
    await screen.findByText("Statusseite");
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    await userEvent.click(screen.getByRole("button", { name: "Secret erneuern" }));
    expect(findCall("POST", "rotate-secret")).toBeUndefined();
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...client, client_secret: "neu-456" }));
    await userEvent.click(screen.getByRole("button", { name: "Secret erneuern" }));
    expect(await screen.findByText("neu-456")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(findCall("POST", "/platform/oidc-clients/status/rotate-secret")).toBeDefined();
  });

  it("deactivates and activates a client", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([client]));
    renderIntl(<OidcClientsAdmin />);
    await screen.findByText("Statusseite");
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...client, active: false })).mockResolvedValueOnce(jsonResponse([{ ...client, active: false }]));
    await userEvent.click(screen.getByRole("button", { name: "Deaktivieren" }));
    await waitFor(() => expect(findCall("POST", "/status/deactivate")).toBeDefined());
    expect(await screen.findByRole("button", { name: "Aktivieren" })).toBeInTheDocument();
    expect(screen.getByText("inaktiv")).toBeInTheDocument();
  });
});
