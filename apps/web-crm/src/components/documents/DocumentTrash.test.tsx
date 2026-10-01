import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DocumentTrash, type TrashEntry } from "./DocumentTrash";

const entry: TrashEntry = {
  document_id: "d1",
  title: "Mietvertrag Altbestand",
  filename: "mv.pdf",
  deleted_at: "2026-10-01T08:00:00Z",
  deleted_by: "u1",
  purge_at: "2026-10-31T08:00:00Z",
  days_left: 30,
  status: "in_trash",
  blocker: null,
};

describe("DocumentTrash (AE33, AC07-03)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("restores a document with a logged reason", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "d1" }));
    renderIntl(<DocumentTrash entries={[entry]} canDelete={true} />);
    expect(screen.getByText("Mietvertrag Altbestand")).toBeInTheDocument();
    expect(screen.getByText(/noch 30 Tage/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Wiederherstellen" }));
    const confirm = screen.getByRole("button", { name: "Wiederherstellung bestätigen" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Begründung/), "Versehentlich gelöscht");
    await userEvent.click(confirm);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/documents/trash/d1/restore");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ reason: "Versehentlich gelöscht" });
    expect(await screen.findByText("Dokument wiederhergestellt.")).toBeInTheDocument();
    expect(screen.getByText("Der Papierkorb ist leer.")).toBeInTheDocument();
  });

  it("purges early only after a confirmation with reason and blocks a held document", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    const held: TrashEntry = { ...entry, document_id: "d2", title: "Gesperrte Akte", status: "held", blocker: "Löschungssperre: Rechtsstreit" };
    renderIntl(<DocumentTrash entries={[entry, held]} canDelete={true} />);
    expect(screen.getByText(/Löschung ausgesetzt: Löschungssperre: Rechtsstreit/)).toBeInTheDocument();
    const [purgeNormal, purgeHeld] = screen.getAllByRole("button", { name: "Endgültig löschen" }) as [HTMLElement, HTMLElement];
    expect(purgeHeld).toBeDisabled();
    await userEvent.click(purgeNormal);
    expect(screen.getByText(/nur noch aus einem Backup umkehren/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Begründung/), "Löschwunsch");
    await userEvent.click(screen.getByRole("button", { name: "Endgültige Löschung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe("/api/bff/documents/trash/d1/purge");
    expect(await screen.findByText(/endgültig gelöscht/)).toBeInTheDocument();
    expect(screen.queryByText("Mietvertrag Altbestand")).not.toBeInTheDocument();
    expect(screen.getByText("Gesperrte Akte")).toBeInTheDocument();
  });

  it("shows the problem message and keeps the row when the server refuses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ code: "MHVP-DOC-0001", title: "Dokument ist aufbewahrungspflichtig oder gesperrt", status: 409 }, 409),
    );
    renderIntl(<DocumentTrash entries={[entry]} canDelete={true} />);
    await userEvent.click(screen.getByRole("button", { name: "Endgültig löschen" }));
    await userEvent.type(screen.getByLabelText(/Begründung/), "Löschwunsch");
    await userEvent.click(screen.getByRole("button", { name: "Endgültige Löschung bestätigen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Mietvertrag Altbestand")).toBeInTheDocument();
  });

  it("hides the actions without the delete right", () => {
    renderIntl(<DocumentTrash entries={[entry]} canDelete={false} />);
    expect(screen.queryByRole("button", { name: "Wiederherstellen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Endgültig löschen" })).not.toBeInTheDocument();
  });
});
