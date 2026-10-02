import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { UnitMasterData } from "./UnitMasterData";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const UNIT = { id: "u1", property_id: "p1", building_id: "b1", version: 1, number: "WE 01", unit_type: "apartment", commission: "1500.00", deposit_amount: "2400.00", sub_community_id: "sc1" };

describe("UnitMasterData", () => {
  it("formats commission and deposit as EUR and has no edit toggle without edit right", () => {
    renderIntl(<UnitMasterData unit={UNIT} canEdit={false} />);
    expect(screen.getByTestId("unit-master-data")).toBeInTheDocument();
    expect(screen.getByText("1.500,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("2.400,00 EUR")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
  });

  it("shows the sub community field only if sub communities exist", () => {
    const { unmount } = renderIntl(<UnitMasterData unit={UNIT} canEdit={false} />);
    expect(screen.queryByText("Untergemeinschaft")).not.toBeInTheDocument();
    unmount();
    renderIntl(<UnitMasterData unit={UNIT} canEdit={false} subCommunities={[{ id: "sc1", code: "TG", name: "Tiefgarage" }]} />);
    expect(screen.getByText("Untergemeinschaft")).toBeInTheDocument();
    expect(screen.getByText("TG Tiefgarage")).toBeInTheDocument();
  });
});
