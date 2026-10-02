import { render, screen } from "@testing-library/react";

import { SAFE_HTML_CLASS, SAFE_LINE_CLASS, SAFE_TEXT_CLASS, SafeHtml, SafeLine, SafeText } from "./SafeText";

describe("SafeText (GAI-615)", () => {
  it("wraps text and lines so long strings cannot widen the page", () => {
    render(
      <>
        <SafeText testId="t" className="extra">{"a".repeat(300)}</SafeText>
        <SafeLine testId="l">{"https://example.invalid/" + "b".repeat(200)}</SafeLine>
      </>,
    );
    expect(screen.getByTestId("t")).toHaveClass("extra");
    for (const cls of SAFE_TEXT_CLASS.split(" ")) expect(screen.getByTestId("t")).toHaveClass(cls);
    for (const cls of SAFE_LINE_CLASS.split(" ")) expect(screen.getByTestId("l")).toHaveClass(cls);
  });

  it("renders the given markup inside the scrolling container", () => {
    render(<SafeHtml testId="h" html="<p>Hallo <b>Welt</b></p>" />);
    expect(screen.getByTestId("h")).toHaveClass(...SAFE_HTML_CLASS.split(" ").slice(0, 2));
    expect(screen.getByTestId("h").querySelector("b")).toHaveTextContent("Welt");
  });
});
