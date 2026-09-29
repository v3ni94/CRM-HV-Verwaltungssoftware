import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { HandoverReadCard } from "./HandoverReadCard";
import { protocol } from "./HandoverFill.test.fixture";

const files = "/api/portal-files/portal/handover/0192abcd-0000-7000-8000-000000000070";

describe("HandoverReadCard (Beteiligter im Lesefenster, M30-06)", () => {
  it("renders the data as text without inputs, versions, internal fields or a new tab", async () => {
    const { container } = renderIntl(
      <HandoverReadCard
        files={files}
        p={protocol({
          status: "completed",
          locked: true,
          finalized: true,
          handover_date: "2026-09-20",
          handover_start: "10:00:00",
          access: { right: "read", valid_to: "2026-10-04" },
          rooms: [{ id: "r1", name: "Küche", room_type: null, condition: "defective", comment: null, sort_order: 0 }],
          defects: [
            { id: "d1", room_id: "r1", category: "Wand", title: "Riss", description: "Riss über der Tür", priority: "low", defect_status: "new", location: null, responsibility: null },
            { id: "d2", room_id: null, category: "Sonstiges", title: "Klingel defekt", description: null, priority: "info", defect_status: "new", location: null, responsibility: null },
          ],
          meters: [{ id: "m1", meter_type: "electricity", custom_type: null, number: "4711", value: "1234.5", unit: "kWh", read_on: "2026-09-20", location: null, comment: null }],
          documents: [
            { id: "doc1", title: "Riss Foto", filename: "riss.jpg", mime_type: "image/jpeg", size: 10, kind: "photo", section: "defects", item_id: "d1", created_at: "2026-09-20T10:00:00Z" },
          ],
          signatures: [
            { id: "s1", participant_id: null, signer_name: "Erika Muster", signer_role: "moving_in", sha256: "abcdef0123456789", signed_at: "2026-09-20T11:00:00Z", signed_location: null, document_id: "sig1" },
          ],
        })}
      />,
    );
    expect(screen.getByTestId("handover-read")).toBeInTheDocument();
    expect(container.querySelectorAll("input, select, textarea")).toHaveLength(0);
    expect(container.querySelector("a[target]")).toBeNull();
    expect(screen.getByText("Übergabe am 20.09.2026, 10:00")).toBeInTheDocument();
    expect(screen.getByText("Küche")).toBeInTheDocument();
    expect(screen.getByText("Wand: Riss")).toBeInTheDocument();
    expect(screen.getByText("Ohne Raumzuordnung")).toBeInTheDocument();
    expect(screen.getByText("Sonstiges: Klingel defekt")).toBeInTheDocument();
    expect(screen.getByText(/4711/)).toBeInTheDocument();
    expect(screen.getByText(/Erika Muster/)).toBeInTheDocument();
    expect(screen.getByText("unterschrieben am 20.09.2026")).toBeInTheDocument();
    expect(screen.getByText("Protokoll als PDF")).toHaveAttribute("href", `${files}/pdf`);
    expect(screen.getByText("Nur lesen, abrufbar bis 04.10.2026")).toBeInTheDocument();
    // M30-06: no internal remarks, no administration number, no version or cancellation.
    expect(screen.queryByText(/intern/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Verwaltungsnummer|Storno|Fassung/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Foto Riss Foto vergrößern" }));
    expect(screen.getByRole("dialog", { name: "Riss Foto" })).toBeInTheDocument();
  });
});
