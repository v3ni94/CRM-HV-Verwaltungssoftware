import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";

import de from "../../../messages/de.json";
import { DocumentBundleList } from "./DocumentBundleList";

const rows = [
  { id: "a", title: "Vertrag", filename: "v.pdf", created_at: "2026-01-01T00:00:00Z", is_new: true },
  { id: "b", title: "Nachweis", filename: "n.pdf", created_at: "2026-01-02T00:00:00Z", is_new: false },
];

function renderList() {
  return render(
    <NextIntlClientProvider locale="de" messages={de}>
      <DocumentBundleList rows={rows} formatDate={(v) => v.slice(0, 10)} />
    </NextIntlClientProvider>,
  );
}

describe("DocumentBundleList", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("formats dates itself, so the server page passes no function (GAJ-403)", () => {
    render(
      <NextIntlClientProvider locale="de" messages={de} timeZone="Europe/Berlin">
        <DocumentBundleList rows={rows} />
      </NextIntlClientProvider>,
    );
    expect(screen.getByText(/01\.01\.2026/)).toBeInTheDocument();
  });

  it("disables the bundle button until documents are selected and posts the chosen ids", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["zip"]) });
    vi.stubGlobal("fetch", fetchMock);
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    renderList();
    const button = screen.getByRole("button", { name: /Sammel-Download/ });
    expect(button).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /Nachweis/ }));
    expect(button).toBeEnabled();
    await user.click(button);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, { body: string }];
    expect(url).toBe("/api/bff/portal/documents/bundle");
    expect(JSON.parse(init.body)).toEqual({ document_ids: ["b"] });
  });

  it("shows an error when the bundle is refused", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    renderList();
    await user.click(screen.getByRole("checkbox", { name: /Vertrag/ }));
    await user.click(screen.getByRole("button", { name: /Sammel-Download/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sammel-Download");
  });
});
