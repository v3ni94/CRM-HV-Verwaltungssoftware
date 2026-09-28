import { render, screen } from "@testing-library/react";

import { KeyValueList } from "./KeyValueList";

describe("KeyValueList", () => {
  it("renders a two column definition list that stacks without overflow", () => {
    render(
      <KeyValueList
        testId="unit-facts"
        items={[
          { label: "Nummer", value: "WE 12", testId: "unit-number" },
          { label: "Fläche", value: "72,50 m²", num: true },
          { label: "IBAN", value: "DE00000000000000000000" },
        ]}
      />,
    );
    const list = screen.getByTestId("unit-facts");
    expect(list.tagName).toBe("DL");
    expect(list).toHaveClass("grid", "grid-cols-[minmax(0,1fr)_auto]", "sm:grid-cols-[12rem_minmax(0,1fr)]");
    expect(list.querySelectorAll("dt")).toHaveLength(3);
    expect(list.querySelectorAll("dd")).toHaveLength(3);
    expect(screen.getByText("Nummer").tagName).toBe("DT");
    const number = screen.getByTestId("unit-number");
    expect(number.tagName).toBe("DD");
    expect(number).toHaveClass("min-w-0", "break-words");
    expect(screen.getByText("72,50 m²")).toHaveClass("mhvp-num", "text-right");
    expect(screen.getByText("DE00000000000000000000")).not.toHaveClass("mhvp-num");
  });

  it("marks every value numeric with the list option", () => {
    render(<KeyValueList num items={[{ label: "Betrag", value: "1.234,56 EUR" }]} />);
    expect(screen.getByText("1.234,56 EUR")).toHaveClass("mhvp-num");
  });

  it("renders an empty list without error", () => {
    render(<KeyValueList items={[]} testId="empty" />);
    expect(screen.getByTestId("empty")).toBeEmptyDOMElement();
  });
});
