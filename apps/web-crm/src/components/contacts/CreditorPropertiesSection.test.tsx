import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { CreditorPropertiesSection } from "./CreditorPropertiesSection";

describe("CreditorPropertiesSection", () => {
  it("shows the empty state", () => {
    renderIntl(<CreditorPropertiesSection rows={[]} />);
    expect(screen.getByText("An keinem Objekt als Dienstleister verknüpft.")).toBeInTheDocument();
  });

  it("lists properties with trade, start and source", () => {
    renderIntl(
      <CreditorPropertiesSection
        rows={[{ id: "l1", property_id: "11111111-1111-1111-1111-111111111111", property_number: "801", property_name: "Testweg 1", trade: "Sanitär", since: "2024-03-01", source: "backfill" }]}
      />,
    );
    expect(screen.getByRole("link", { name: "801 Testweg 1" })).toHaveAttribute("href", "/objekte/11111111-1111-1111-1111-111111111111#dienstleister");
    expect(screen.getByText("Sanitär")).toBeInTheDocument();
    expect(screen.getByText("01.03.2024")).toBeInTheDocument();
    expect(screen.getByText("nachgezogen")).toBeInTheDocument();
  });
});
