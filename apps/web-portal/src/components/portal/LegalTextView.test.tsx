import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { LegalTextView } from "./LegalTextView";

const base = { code: "impressum" as const, version: null, title: null, body: null, externalUrl: null, termsVersion: null };

describe("LegalTextView", () => {
  it("shows the approved text with its version", () => {
    renderIntl(<LegalTextView text={{ ...base, released: true, version: 3, title: "Impressum", body: "Zeile 1\nZeile 2" }} />);
    expect(screen.getByRole("heading", { name: "Impressum" })).toBeInTheDocument();
    expect(screen.getByText("Fassung 3")).toBeInTheDocument();
    expect(screen.getByText(/Zeile 1/)).toBeInTheDocument();
    expect(screen.queryByText("Text nicht freigegeben")).toBeNull();
  });

  it("shows the marker and the external link while nothing is released", () => {
    renderIntl(<LegalTextView text={{ ...base, code: "datenschutz", released: false, externalUrl: "https://example.test/dsgvo" }} />);
    expect(screen.getByRole("heading", { name: "Datenschutzerklärung" })).toBeInTheDocument();
    expect(screen.getByText("Text nicht freigegeben")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Text beim Anbieter öffnen" })).toHaveAttribute("href", "https://example.test/dsgvo");
  });

  it("shows the terms label of the consent policy for the terms text", () => {
    renderIntl(
      <LegalTextView text={{ ...base, code: "nutzungsbedingungen", released: true, version: 2, title: "NB", body: "x", termsVersion: "NB-2" }} />,
    );
    expect(screen.getByText(/Version der Einwilligungsrichtlinie: NB-2/)).toBeInTheDocument();
  });

  it("reports a failed load", () => {
    renderIntl(<LegalTextView text={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("konnte gerade nicht geladen werden");
  });
});
