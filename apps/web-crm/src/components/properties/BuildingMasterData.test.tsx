import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { BuildingMasterData } from "./BuildingMasterData";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const BUILDING = { id: "b1", property_id: "p1", version: 1, name: "Haus A", total_area_sqm: "1250.5", floors: 3 };

describe("BuildingMasterData", () => {
  it("shows the values formatted and without edit button for read only users", () => {
    renderIntl(<BuildingMasterData building={BUILDING} canEdit={false} />);
    expect(screen.getByTestId("building-master-data")).toBeInTheDocument();
    expect(screen.getByText("Haus A")).toBeInTheDocument();
    expect(screen.getByText("1.250,50 m²")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
  });

  it("offers the edit toggle with edit right", () => {
    renderIntl(<BuildingMasterData building={BUILDING} canEdit />);
    expect(screen.getByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });
});
