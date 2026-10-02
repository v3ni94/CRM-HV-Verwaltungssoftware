import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { UprotokollFiles } from "./UprotokollFiles";

const list = (linked: [string, string][]) => ({
  items: [{ document_id: "d1", filename: "foto.jpg", file_category: "photo", protocol_id: "p1", linked }],
  total: 1,
  pending_files: ["offen.jpg"],
});

describe("UprotokollFiles Liste und Lösen", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lädt Zuordnungen und löst eine Datei", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      const released = fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "DELETE");
      return Promise.resolve(jsonResponse(list(released ? [] : [["handover_protocol", "p1"]])));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<UprotokollFiles canMatch />);
    await act(async () => {
      await userEvent.type(screen.getByLabelText("Lauf ID"), "run-1");
      await userEvent.click(screen.getByTestId("uprotokoll-files-load"));
    });
    expect(await screen.findByText("foto.jpg")).toBeInTheDocument();
    expect(screen.getByText("offen.jpg")).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Lösen" }));
    });
    expect(await screen.findByText("gelöst")).toBeInTheDocument();
    const del = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "DELETE");
    expect(del?.[0]).toContain("/api/bff/handover/imports/uprotokoll/files/d1?import_run_id=run-1");
  });

  it("zeigt den Fehler beim Lösen und blendet Lösen ohne Recht aus", async () => {
    const fetchMock = vi.fn().mockImplementation((_u: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "DELETE" ? jsonResponse({ detail: "Signatur" }, 409) : jsonResponse(list([["handover_protocol", "p1"]]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = renderIntl(<UprotokollFiles canMatch />);
    await act(async () => {
      await userEvent.type(screen.getByLabelText("Lauf ID"), "run-1");
      await userEvent.click(screen.getByTestId("uprotokoll-files-load"));
    });
    await act(async () => {
      await userEvent.click(await screen.findByRole("button", { name: "Lösen" }));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    unmount();
    renderIntl(<UprotokollFiles canMatch={false} />);
    await act(async () => {
      await userEvent.type(screen.getByLabelText("Lauf ID"), "run-1");
      await userEvent.click(screen.getByTestId("uprotokoll-files-load"));
    });
    await screen.findByText("foto.jpg");
    expect(screen.queryByRole("button", { name: "Lösen" })).toBeNull();
  });
});
