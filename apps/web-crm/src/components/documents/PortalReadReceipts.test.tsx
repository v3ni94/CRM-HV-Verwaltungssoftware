import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { PortalReadReceipts } from "./PortalReadReceipts";

const NOTE = "Indiz für den Abruf über das Portal. Keine Zustellung und kein rechtlich bewerteter Zugang.";

describe("PortalReadReceipts", () => {
  it("shows the legal note and the empty state", () => {
    renderIntl(<PortalReadReceipts data={{ document_id: "d1", note: NOTE, items: [] }} />);
    expect(screen.getByText("Indiz, keine Zustellung, keine Rechtsfolge.")).toBeInTheDocument();
    expect(screen.getByText(NOTE)).toBeInTheDocument();
    expect(screen.getByText("Keine Abrufe über das Portal.")).toBeInTheDocument();
  });

  it("lists time, kind and account per receipt", () => {
    renderIntl(
      <PortalReadReceipts
        data={{
          document_id: "d1",
          note: NOTE,
          items: [
            { id: "r1", account_id: "a1", contact_id: "c1", kind: "downloaded", occurred_at: "2026-09-26T08:15:00Z" },
            { id: "r2", account_id: "a1", contact_id: "c2", kind: "opened", occurred_at: "2026-09-25T06:00:00Z" },
          ],
        }}
        contactNames={{ c1: "Erika Muster" }}
      />,
    );
    expect(screen.getByText("heruntergeladen")).toBeInTheDocument();
    expect(screen.getByText("angezeigt")).toBeInTheDocument();
    expect(screen.getByText("Erika Muster")).toBeInTheDocument();
    expect(screen.getByText("c2")).toBeInTheDocument();
    expect(screen.getByText(/26\.09\.2026 10:15/)).toBeInTheDocument();
  });
});
