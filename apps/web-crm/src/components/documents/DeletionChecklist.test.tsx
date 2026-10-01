import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DeletionChecklist } from "./DeletionChecklist";

const open = {
  document_id: "d1",
  status: "open",
  items: [
    { target: "index", status: "done", detail: null },
    { target: "mirror_google_drive", status: "open", detail: null },
    { target: "backup", status: "out_of_scope", detail: null },
  ],
};

describe("DeletionChecklist (AC07, GA08-08)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows targets and runs the follow up", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(open))
      .mockResolvedValueOnce(jsonResponse({ ...open, status: "done", items: [] }));
    renderIntl(<DeletionChecklist documentId="d1" canDelete={true} />);
    await userEvent.click(screen.getByRole("button", { name: "Löschcheckliste" }));
    expect(await screen.findByText(/Google Drive: offen/)).toBeInTheDocument();
    expect(screen.getByText(/Backups: nicht bearbeitet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Nachlauf starten" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/bff/documents/deletions/d1/follow-up");
    expect(init.method).toBe("POST");
    expect(await screen.findByText("Alle Ziele gelöscht.")).toBeInTheDocument();
  });

  it("shows a document in the trash (AE33) without a follow up button", async () => {
    const inTrash = {
      document_id: "d1",
      status: "in_trash",
      items: [
        { target: "trash", status: "open", detail: "Im Papierkorb, endgültige Löschung frühestens am 31.10.2026." },
        { target: "index", status: "pending", detail: null },
      ],
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(inTrash));
    renderIntl(<DeletionChecklist documentId="d1" canDelete={true} />);
    await userEvent.click(screen.getByRole("button", { name: "Löschcheckliste" }));
    expect(await screen.findByText(/Im Papierkorb, die endgültige Löschung folgt/)).toBeInTheDocument();
    expect(screen.getByText(/Papierkorb: offen/)).toBeInTheDocument();
    expect(screen.getByText(/Index und Volltext: folgt/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nachlauf starten" })).not.toBeInTheDocument();
  });

  it("hides the follow up without delete right", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(open));
    renderIntl(<DeletionChecklist documentId="d1" canDelete={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Löschcheckliste" }));
    await screen.findByText(/Google Drive: offen/);
    expect(screen.queryByRole("button", { name: "Nachlauf starten" })).not.toBeInTheDocument();
  });
});
