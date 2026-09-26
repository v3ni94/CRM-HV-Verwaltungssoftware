import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { DmsObjectTile } from "./DmsObjectTile";

describe("DmsObjectTile", () => {
  it("shows status, open cases, completeness and missing documents", () => {
    renderIntl(
      <DmsObjectTile
        object={{
          number: "291",
          name: "Haus DMS",
          archived: false,
          takeover_status: "in_progress",
          open_review_cases: 3,
          completeness: { required: 10, present: 7, missing: 3, percent: 70 },
          drive_folder_id: "f",
          drive_folder_url: null,
          updated_at: null,
          property_id: null,
        }}
      />,
    );
    const tile = screen.getByTestId("dms-tile");
    expect(tile).toHaveAttribute("href", "/dms/291");
    expect(tile).toHaveTextContent("Haus DMS");
    expect(tile).toHaveTextContent("in_progress");
    expect(tile).toHaveTextContent("70 %");
    expect(tile).toHaveTextContent("7 von 10 Unterlagen");
    expect(tile).toHaveTextContent("Nicht im CRM angelegt");
  });
});
