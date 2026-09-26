import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { DocumentListFilter, draftFilterOf } from "./DocumentListFilter";

describe("DocumentListFilter", () => {
  it("offers all, only drafts and without drafts and keeps the current selection", () => {
    renderIntl(<DocumentListFilter q="Miete" draft="true" />);
    const select = screen.getByLabelText("Entwürfe") as HTMLSelectElement;
    expect(select.value).toBe("true");
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Alle", "nur Entwürfe", "ohne Entwürfe"]);
    expect((screen.getByLabelText("Suche") as HTMLInputElement).value).toBe("Miete");
  });

  it("maps unknown URL values to no filter", () => {
    expect(draftFilterOf(undefined)).toBe("");
    expect(draftFilterOf("x")).toBe("");
    expect(draftFilterOf("false")).toBe("false");
  });
});
