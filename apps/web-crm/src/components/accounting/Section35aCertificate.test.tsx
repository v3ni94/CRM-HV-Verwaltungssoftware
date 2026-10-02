import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { Section35aCertificate } from "./Section35aCertificate";

const CID = "01920000-0000-7000-8000-00000000c001";

describe("Section35aCertificate", () => {
  afterEach(() => vi.restoreAllMocks());

  it("calculates and offers the PDF draft", async () => {
    const urls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      urls.push(String(input));
      return jsonResponse({
        contract_id: CID,
        year: 2025,
        share_percent: "100",
        labor_total: "1200.00",
        material_total: "300.00",
        labor_by_kind: {},
        notice: "Entwurf",
      });
    });
    renderIntl(<Section35aCertificate />);
    expect(screen.getByRole("button", { name: "Berechnen" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Vertrag (Kennung aus der Vertragsseite)"), CID);
    await userEvent.click(screen.getByRole("button", { name: "Berechnen" }));
    expect(await screen.findByTestId("s35a-result")).toHaveTextContent("1.200,00 EUR");
    expect(urls[0]).toContain(`contract_id=${CID}`);
    expect(screen.getByTestId("s35a-pdf").getAttribute("href")).toContain("certificate.pdf?contract_id=");
  });
});
