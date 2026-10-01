import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ChatTools } from "./ChatTools";

const wrap = renderIntl;

describe("ChatTools", () => {
  it("lists the lookups with masked search text and hit count", () => {
    wrap(
      <ChatTools
        tools={[
          { tool: "kontakte", label: "Kontakte", arguments: { suche: "Meier [E-Mail]" }, permitted: true, count: 2 },
          { tool: "kontenplan", label: "Kontenplan", arguments: {}, permitted: false, count: 0 },
        ]}
      />,
    );
    expect(screen.getByText("Verwendete Nachschlagewerkzeuge")).toBeInTheDocument();
    expect(screen.getByText(/Meier \[E-Mail\]/)).toBeInTheDocument();
    expect(screen.getByText(/2 Treffer/)).toBeInTheDocument();
    expect(screen.getByText(/ohne Berechtigung/)).toBeInTheDocument();
  });

  it("renders nothing without tools", () => {
    const { container } = wrap(<ChatTools tools={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
