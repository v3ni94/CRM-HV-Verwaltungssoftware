import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OpenImmoExport } from "./OpenImmoExport";

const LISTING_ID = "0192abcd-0000-7000-8000-000000000060";
const MISSING = {
  field: "price",
  label: "Kaltmiete bzw. Kaufpreis",
  path: "preise/kaltmiete bzw. preise/kaufpreis",
  message: "Preis fehlt (Kaltmiete bzw. Kaufpreis, preise).",
};

describe("OpenImmoExport", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows missing fields and no download link when the check finds gaps", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ complete: false, missing: [MISSING], warnings: [MISSING.message], hints: [], image_count: 0 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vollständigkeit prüfen" }));

    await waitFor(() => expect(screen.getByTestId("openimmo-warnings")).toBeInTheDocument());
    expect(screen.getByText("Kaltmiete bzw. Kaufpreis")).toBeInTheDocument();
    expect(screen.getByText(/Preis fehlt \(Kaltmiete bzw. Kaufpreis, preise\)\./)).toBeInTheDocument();
    expect(screen.queryByTestId("openimmo-download")).not.toBeInTheDocument();
    expect(screen.queryByTestId("openimmo-download-zip")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`/api/bff/letting/listings/${LISTING_ID}/openimmo-check`, expect.anything());
  });

  it("offers the forced download once 'trotzdem exportieren' is ticked", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ complete: false, missing: [MISSING], warnings: [MISSING.message], hints: [], image_count: 2 }),
      ),
    );

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vollständigkeit prüfen" }));
    await screen.findByTestId("openimmo-warnings");
    await userEvent.click(screen.getByTestId("openimmo-force"));

    const xml = await screen.findByTestId("openimmo-download");
    expect(xml).toHaveAttribute("href", `/api/bff/letting/listings/${LISTING_ID}/openimmo.xml?force=true`);
    const zip = screen.getByTestId("openimmo-download-zip");
    expect(zip).toHaveAttribute("href", `/api/bff/letting/listings/${LISTING_ID}/openimmo.zip?force=true`);
    expect(zip).toHaveTextContent("ZIP mit 2 Bildern herunterladen");
  });

  it("offers XML and ZIP downloads and hints once the check passes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          complete: true,
          missing: [],
          warnings: [],
          hints: ["Energieträger ist nicht angegeben (energiepass/primaerenergietraeger)."],
          image_count: 0,
        }),
      ),
    );

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vollständigkeit prüfen" }));

    const link = await screen.findByTestId("openimmo-download");
    expect(link).toHaveAttribute("href", `/api/bff/letting/listings/${LISTING_ID}/openimmo.xml`);
    expect(screen.getByTestId("openimmo-download-zip")).toHaveAttribute(
      "href",
      `/api/bff/letting/listings/${LISTING_ID}/openimmo.zip`,
    );
    expect(screen.getByText("Alle Pflichtfelder sind vorhanden. Der Export kann heruntergeladen werden.")).toBeInTheDocument();
    expect(screen.getByTestId("openimmo-hints")).toHaveTextContent("Energieträger ist nicht angegeben");
    expect(screen.queryByTestId("openimmo-force")).not.toBeInTheDocument();
  });

  it("shows the structural check with the operator notice when no XSD is stored", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          complete: true,
          missing: [],
          warnings: [],
          hints: [],
          image_count: 0,
          schema: {
            mode: "structure",
            valid: true,
            errors: [],
            notice: "OpenImmo-XSD nicht hinterlegt. Die Datei wird nur strukturell geprüft.",
            xsd_configured: false,
          },
        }),
      ),
    );

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vollständigkeit prüfen" }));

    await screen.findByTestId("openimmo-download");
    expect(screen.getByTestId("openimmo-schema")).toHaveTextContent("Strukturprüfung bestanden");
    expect(screen.getByTestId("openimmo-schema-notice")).toHaveTextContent("OpenImmo-XSD nicht hinterlegt");
    expect(screen.queryByTestId("openimmo-schema-errors")).not.toBeInTheDocument();
    expect(screen.queryByTestId("openimmo-force")).not.toBeInTheDocument();
  });

  it("locks the download on schema errors until 'trotzdem exportieren' is ticked", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          complete: true,
          missing: [],
          warnings: [],
          hints: [],
          image_count: 0,
          schema: {
            mode: "xsd",
            valid: false,
            errors: ["Zeile 3: Element 'geo' fehlt."],
            notice: null,
            xsd_configured: true,
          },
        }),
      ),
    );

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vollständigkeit prüfen" }));

    await screen.findByTestId("openimmo-schema");
    expect(screen.getByTestId("openimmo-schema")).toHaveTextContent(
      "Schemaprüfung gegen die hinterlegte OpenImmo-XSD nicht bestanden",
    );
    expect(screen.getByTestId("openimmo-schema-errors")).toHaveTextContent("Zeile 3: Element 'geo' fehlt.");
    expect(screen.queryByTestId("openimmo-warnings")).not.toBeInTheDocument();
    expect(screen.queryByTestId("openimmo-download")).not.toBeInTheDocument();
    expect(screen.queryByText("Alle Pflichtfelder sind vorhanden. Der Export kann heruntergeladen werden.")).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId("openimmo-force"));
    const xml = await screen.findByTestId("openimmo-download");
    expect(xml).toHaveAttribute("href", `/api/bff/letting/listings/${LISTING_ID}/openimmo.xml?force=true`);
  });

  it("shows an error message when the check request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Fehler", detail: "kaputt" }, 500)));

    renderIntl(<OpenImmoExport listingId={LISTING_ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vollständigkeit prüfen" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByTestId("openimmo-download")).not.toBeInTheDocument();
  });
});
