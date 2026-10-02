import { screen } from "@testing-library/react";

import { IntlTestProvider, renderIntl } from "@/test/intl";

import { AttentionBadge, AttentionLegend } from "./TicketAttention";

const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000 - 60_000).toISOString();

describe("TicketAttention", () => {
  it("renders nothing for level none", () => {
    const { container } = renderIntl(<AttentionBadge attention="none" lastActivityAt={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("labels closed and new tickets without time", () => {
    const { rerender } = renderIntl(<AttentionBadge attention="closed" lastActivityAt={null} />);
    expect(screen.getByTestId("attention-label")).toHaveTextContent("Erledigt");
    expect(screen.getByTestId("attention-label")).toHaveAttribute("data-attention", "closed");
    rerender(<IntlTestProvider><AttentionBadge attention="new" lastActivityAt={null} /></IntlTestProvider>);
    expect(screen.getByTestId("attention-label")).toHaveTextContent("Neu, noch ohne Reaktion");
  });

  it("switches from hours to days at 48 hours", () => {
    const { rerender } = renderIntl(<AttentionBadge attention="stale_24h" lastActivityAt={hoursAgo(30)} />);
    expect(screen.getByTestId("attention-label")).toHaveTextContent("Seit 30 Stunden ohne Reaktion");
    rerender(<IntlTestProvider><AttentionBadge attention="stale_96h" lastActivityAt={hoursAgo(100)} /></IntlTestProvider>);
    expect(screen.getByTestId("attention-label")).toHaveTextContent("Seit 4 Tagen ohne Reaktion");
  });

  it("lists the four legend levels", () => {
    renderIntl(<AttentionLegend />);
    const legend = screen.getByTestId("attention-legend");
    expect(legend).toHaveAccessibleName("Farblegende");
    expect(legend.querySelectorAll("li")).toHaveLength(4);
    expect(legend).toHaveTextContent("Rot: seit 96 Stunden");
    expect(legend).toHaveTextContent("Grün: erledigt");
  });
});
