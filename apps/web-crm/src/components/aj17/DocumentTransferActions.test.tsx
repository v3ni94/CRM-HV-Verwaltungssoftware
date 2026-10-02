import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DocumentTransferActions } from "./DocumentTransferActions";

describe("DocumentTransferActions (GAI-417)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a signed download link", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ url: "https://files.example/x?sig=1", expires_in: 300 }));
    renderIntl(<DocumentTransferActions documentId="01920000-0000-7000-8000-0000000a1701" canMirror={false} />);
    expect(screen.queryByRole("button", { name: "Spiegelung erneut anstoßen" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Download-Link erzeugen" }));
    expect(await screen.findByRole("link", { name: "Datei öffnen" })).toHaveAttribute("href", "https://files.example/x?sig=1");
    expect(screen.getByTestId("download-link")).toHaveTextContent("300 Sekunden");
    expect(f.mock.calls[0]![0]).toBe("/api/bff/documents/01920000-0000-7000-8000-0000000a1701/download-url");
  });

  it("triggers the mirror and shows errors", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: "01920000-0000-7000-8000-0000000a1701" }));
    renderIntl(<DocumentTransferActions documentId="01920000-0000-7000-8000-0000000a1701" canMirror />);
    await userEvent.click(screen.getByRole("button", { name: "Spiegelung erneut anstoßen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Spiegelung angestoßen.");
    expect(f.mock.calls[0]![0]).toBe("/api/bff/documents/01920000-0000-7000-8000-0000000a1701/mirror");
    f.mockResolvedValueOnce(jsonResponse({ title: "Fehler", status: 404 }, 404));
    await userEvent.click(screen.getByRole("button", { name: "Download-Link erzeugen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
