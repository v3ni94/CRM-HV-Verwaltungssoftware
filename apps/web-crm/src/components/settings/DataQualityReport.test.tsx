import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { type DataQualityReportData, DataQualityReport } from "./DataQualityReport";

const REPORT: DataQualityReportData = {
  generated_on: "2026-10-01",
  sections_omitted: ["deadlines"],
  sections: [
    {
      key: "contacts",
      total: 5,
      items: [{ entity_type: "contact", entity_id: "c1", label: "Max Muster", findings: [{ rule: "ES-02", field: "last_name", severity: "warning", message: "Name vermutlich vertauscht" }] }],
    },
    { key: "properties", total: 0, items: [] },
  ],
};

describe("DataQualityReport (GAI-615)", () => {
  it("shows the load error without a report", () => {
    renderIntl(<DataQualityReport report={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Der Bericht konnte nicht geladen werden.");
  });

  it("lists findings with severity, link to the record, counts and omitted sections", () => {
    renderIntl(<DataQualityReport report={REPORT} />);
    expect(screen.getByText("Stand 01.10.2026", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Ohne Berechtigung ausgeblendet: Fristen ohne verantwortliche Person/)).toBeInTheDocument();
    const contacts = screen.getByTestId("dq-contacts");
    expect(contacts).toHaveTextContent("1 von 5");
    expect(contacts).toHaveTextContent("Warnung ES-02: Name vermutlich vertauscht");
    expect(contacts.querySelector("a")).toHaveAttribute("href", "/kontakte/c1");
    expect(screen.getByTestId("dq-properties")).toHaveTextContent("Keine Abweichungen gefunden.");
  });
});
