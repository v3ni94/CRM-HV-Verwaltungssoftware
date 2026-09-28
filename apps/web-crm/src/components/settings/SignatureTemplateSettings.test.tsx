import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { SignatureTemplateSettings } from "./SignatureTemplateSettings";

describe("SignatureTemplateSettings", () => {
  it("says that mails go out as plain text and the HTML template only feeds the preview (review 1.36.0)", () => {
    renderIntl(<SignatureTemplateSettings initial={{ text: null, html: "<p>{name}</p>", logo_url: null }} canUpdate={true} />);
    expect(screen.getByLabelText("HTML-Vorlage (derzeit nicht im Versand verwendet)")).toHaveValue("<p>{name}</p>");
    expect(screen.getByTestId("signature-template-html-hint")).toHaveTextContent(
      "E-Mails werden derzeit als Klartext mit der Textvorlage versendet.",
    );
    expect(screen.getByText(/nur in der HTML-Vorschau/)).toBeInTheDocument();
  });

  it("shows the placeholder examples literally instead of formatting them as ICU arguments", () => {
    renderIntl(<SignatureTemplateSettings initial={{ text: null, html: null, logo_url: null }} canUpdate={true} />);
    expect(screen.getByLabelText("Textvorlage")).toHaveAttribute("placeholder", "{name}\n{position}\n{company}\n...");
    expect(screen.getByLabelText("HTML-Vorlage (derzeit nicht im Versand verwendet)")).toHaveAttribute("placeholder", "<p>{name}<br>{position}</p>");
  });
});
