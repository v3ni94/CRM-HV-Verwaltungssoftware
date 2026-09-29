import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { TicketFlowPanel } from "./TicketFlowPanel";
import { PROCESS_CODES, TicketProcessBadge, isProcessCode } from "./TicketProcessBadge";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

describe("TicketProcessBadge", () => {
  it("shows the German label of a catalogue code with the confidence", () => {
    renderIntl(<TicketProcessBadge code="kuendigung" confidence={0.9} />);
    expect(screen.getByTestId("ticket-process-badge")).toHaveAttribute("data-process", "kuendigung");
    expect(screen.getByText("Kündigung (90%)")).toBeInTheDocument();
  });

  it("renders nothing without a code and the raw code when unknown", () => {
    const { container } = renderIntl(<TicketProcessBadge code={null} />);
    expect(container).toBeEmptyDOMElement();
    renderIntl(<TicketProcessBadge code="sonderfall" />);
    expect(screen.getByText("sonderfall")).toBeInTheDocument();
  });

  it("knows exactly the twelve catalogue codes", () => {
    expect(PROCESS_CODES).toHaveLength(12);
    expect(isProcessCode("kaution")).toBe(true);
    expect(isProcessCode("iban")).toBe(false);
  });
});

describe("TicketFlowPanel", () => {
  it("shows role, link status, deadline proposals and documents of an applied flow", () => {
    renderIntl(
      <TicketFlowPanel
        ticketId="01920000-0000-7000-8000-00000000000a"
        processCode="kuendigung"
        flow={{
          process_code: "kuendigung",
          responsible_role: "standard",
          required_links: ["contact", "contract"],
          links: { contact: true, contract: false },
          deadline_proposals: [{ type: "move_out", status: "proposed", due_on: null }],
          document_kinds: ["Kündigungsschreiben"],
        }}
        canUpdate={true}
      />,
    );
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(screen.getByTestId("flow-link-contact")).toHaveTextContent("vorhanden");
    expect(screen.getByTestId("flow-link-contract")).toHaveTextContent("fehlt");
    expect(screen.getByTestId("flow-deadline")).toHaveTextContent("Auszug");
    expect(screen.getByText(/Es wird keine Frist automatisch angelegt/)).toBeInTheDocument();
    expect(screen.getByText("Kündigungsschreiben")).toBeInTheDocument();
    expect(screen.queryByTestId("flow-choice")).not.toBeInTheDocument();
  });

  it("offers the catalogue when no flow is applied and the member may update", () => {
    renderIntl(<TicketFlowPanel ticketId="01920000-0000-7000-8000-00000000000a" processCode={null} flow={null} canUpdate={true} />);
    expect(screen.getByTestId("flow-choice")).toBeInTheDocument();
    expect(screen.getByText("Flow anwenden")).toBeDisabled();
  });
});
