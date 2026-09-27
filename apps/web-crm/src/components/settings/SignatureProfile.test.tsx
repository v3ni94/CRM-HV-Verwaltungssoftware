import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { SignatureProfile } from "./SignatureProfile";

const profile = { membership_id: "m1", position: "Objektbetreuung", phone: "02173 12345", mobile_phone: null, catalogue: ["Objektbetreuung"] };
const preview = { membership_id: "m1", text: "-- \nMax Muster\nObjektbetreuung", html: "<p>Max Muster</p>" };

describe("SignatureProfile", () => {
  it("labels the HTML signature as a preview that is not sent (review 1.36.0)", () => {
    renderIntl(<SignatureProfile initialProfile={profile} initialPreview={preview} />);
    expect(screen.getByTestId("signature-text")).toHaveTextContent("Max Muster");
    expect(screen.getByRole("heading", { name: "Vorschau HTML (nicht im Versand)" })).toBeInTheDocument();
    expect(screen.getByTestId("signature-html-hint")).toHaveTextContent(
      "Nur Vorschau. E-Mails werden derzeit als Klartext mit der Textsignatur versendet",
    );
    expect(screen.getByText(/beim Einreichen zur Freigabe automatisch eingefügt/)).toBeInTheDocument();
  });
});
