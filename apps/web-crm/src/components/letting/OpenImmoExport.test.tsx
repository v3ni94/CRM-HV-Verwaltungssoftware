import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OpenImmoExport } from "./OpenImmoExport";

const LISTING_ID = "0192abcd-0000-7000-8000-000000000060";

describe("OpenImmoExport", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows missing fields and no download link when the check finds warnings", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ warnings: ["Preis fehlt (Kaltmiete bzw. Kaufpreis, preise)."] }));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "OpenImmo exportieren" }));

    await waitFor(() => expect(screen.getByTestId("openimmo-warnings")).toBeInTheDocument());
    expect(screen.getByText("Preis fehlt (Kaltmiete bzw. Kaufpreis, preise).")).toBeInTheDocument();
    expect(screen.queryByTestId("openimmo-download")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`/api/bff/letting/listings/${LISTING_ID}/openimmo-check`, expect.anything());
  });

  it("offers the XML download once the check finds nothing missing", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ warnings: [] }));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "OpenImmo exportieren" }));

    const link = await screen.findByTestId("openimmo-download");
    expect(link).toHaveAttribute("href", `/api/bff/letting/listings/${LISTING_ID}/openimmo.xml`);
    expect(screen.getByText("Vollständig für den Export.")).toBeInTheDocument();
  });

  it("shows an error message when the check request fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ title: "Fehler", detail: "kaputt" }, 500));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "OpenImmo exportieren" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByTestId("openimmo-download")).not.toBeInTheDocument();
  });
});
