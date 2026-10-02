import { fireEvent, screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { CircularResolutionForm } from "./CircularResolutionForm";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

const owners = [
  { id: "c1", label: "WE 01" },
  { id: "c2", label: "WE 03" },
];
const basis = [{ id: "r1", number: 4, decided_on: "10.05.2026", subject: "Absenkung Hausordnung" }];

describe("CircularResolutionForm", () => {
  it("keeps the simple majority locked while the tenant switch is off", () => {
    renderIntl(<CircularResolutionForm legalEntityId="e" owners={owners} resolutions={basis} lowerMajorityEnabled={false} />);
    expect(screen.getByText(/nicht freigeschaltet/)).toBeInTheDocument();
    const option = screen.getByRole("option", { name: /einfache Mehrheit/ });
    expect(option).toBeDisabled();
    expect(screen.queryByText("Zulassender Beschluss")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ergebnis feststellen" })).toBeDisabled();
  });

  it("requires the admitting resolution and the deadline for a simple majority", () => {
    renderIntl(<CircularResolutionForm legalEntityId="e" owners={owners} resolutions={basis} lowerMajorityEnabled={true} />);
    const majority = screen.getByLabelText("Zugelassene Mehrheit");
    fireEvent.change(majority, { target: { value: "simple" } });
    expect(screen.getByLabelText("Zulassender Beschluss")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Nr. 4 · 10.05.2026 · Absenkung Hausordnung/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Beschlussgegenstand (Mehrheitsregel)")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByLabelText("Stimme WE 01")).toBeInTheDocument();
  });
});

describe("CircularPortalVotes (AG07)", () => {
  it("lists portal votes read only with the text checksum", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify([{ id: "v1", meeting_id: "m", item_title: "Fassadenanstrich", contract_id: "c1", choice: "yes", cast_at: "2026-11-05T10:00:00Z", wording_sha256: "ab12" }]),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        ),
      ),
    );
    renderIntl(<CircularResolutionForm legalEntityId="e" owners={owners} resolutions={basis} lowerMajorityEnabled={false} />);
    expect(await screen.findByText(/WE 01: Fassadenanstrich, Ja/)).toBeInTheDocument();
    expect(screen.getByText("Prüfsumme des Beschlusstexts: ab12")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
