import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ApiKeysAdmin, type ApiKeyRow } from "./ApiKeysAdmin";

const ID = "11111111-1111-4111-8111-111111111111";
const row: ApiKeyRow = { id: ID, name: "Export", prefix: "ab12cd", scopes: ["contacts:read"], expires_at: null, last_used_at: null, revoked_at: null };

describe("ApiKeysAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the prefix only and revokes after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(null, { status: 204 }));
    renderIntl(<ApiKeysAdmin initial={[row]} canCreate canDelete ownPermissions={["contacts:read"]} />);
    expect(screen.getByText("ab12cd")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Widerrufen" }));
    await waitFor(() => expect(screen.getByTestId(`api-key-${ID}`)).toHaveTextContent("widerrufen"));
    expect(fetchMock.mock.calls[0]![1]?.method).toBe("DELETE");
  });

  it("shows the created key once and removes it on dismissal", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...row, id: "22222222-2222-4222-8222-222222222222", key: "mhvp_geheim_xyz" }));
    renderIntl(<ApiKeysAdmin initial={[]} canCreate canDelete={false} ownPermissions={["contacts:read", "contacts:update"]} />);
    await userEvent.type(screen.getByLabelText("Name"), "Neu");
    await userEvent.click(screen.getByLabelText("contacts:read"));
    expect(screen.queryByLabelText("contacts:update")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Schlüssel erzeugen" }));
    await waitFor(() => expect(screen.getByTestId("secret-once")).toHaveTextContent("mhvp_geheim_xyz"));
    await userEvent.click(screen.getByRole("button", { name: "Ich habe den Wert gesichert" }));
    expect(screen.queryByText("mhvp_geheim_xyz")).not.toBeInTheDocument();
  });

  it("rejects a key without scope", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<ApiKeysAdmin initial={[]} canCreate canDelete={false} ownPermissions={["contacts:read"]} />);
    await userEvent.type(screen.getByLabelText("Name"), "Neu");
    await userEvent.click(screen.getByRole("button", { name: "Schlüssel erzeugen" }));
    expect(screen.getByRole("alert")).toHaveTextContent("mindestens ein Recht");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
