import { render, screen } from "@testing-library/react";
import { createTranslator } from "next-intl";

import { CreditorIdsOverview } from "./CreditorIdsOverview";

vi.mock("next-intl/server", async () => {
  const messages = (await import("../../../messages/de.json")).default;
  return { getTranslations: async (ns: string) => createTranslator({ locale: "de", messages, namespace: ns as never }) };
});

describe("CreditorIdsOverview", () => {
  it("lists stored ids and marks missing ones", async () => {
    render(
      await CreditorIdsOverview({
        rows: [
          { legal_entity_id: "le1", name: "WEG A", sepa_creditor_id: "DE00ZZZ00000000001" },
          { legal_entity_id: null, name: "Mandant", sepa_creditor_id: null },
        ],
      }),
    );
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("WEG A: DE00ZZZ00000000001");
    expect(items[1]).toHaveTextContent("Mandant: nicht hinterlegt");
  });

  it("renders an empty list without rows", async () => {
    render(await CreditorIdsOverview({ rows: [] }));
    expect(screen.getByTestId("creditor-id-overview")).toBeEmptyDOMElement();
  });
});
