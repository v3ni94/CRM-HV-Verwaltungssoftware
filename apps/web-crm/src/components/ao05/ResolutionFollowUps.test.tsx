import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ResolutionFollowUps } from "./ResolutionFollowUps";

const ID = "01920000-0000-7000-8000-0000000a0501";

describe("ResolutionFollowUps (AN19-CRM)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists dependents with the contested flag", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        resolution_id: ID,
        status: "contested",
        contested: true,
        items: [{ type: "special_levy", id: ID, label: "SU 2026", status: "applied", applied: true, contested: true }],
      }),
    );
    renderIntl(<ResolutionFollowUps resolutionId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Folgen prüfen" }));
    expect(await screen.findByTestId("followup-item")).toHaveTextContent("Sonderumlage: SU 2026");
    expect(screen.getByTestId("followup-item")).toHaveTextContent("angefochten");
    expect(f.mock.calls[0]![0]).toBe(`/api/bff/hoa/resolutions/${ID}/dependents`);
  });

  it("creates the review date and states that the duration is not fixed", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ id: ID, due_on: "2026-11-30", due_computed: false, verify: true }, 201),
    );
    renderIntl(<ResolutionFollowUps resolutionId={ID} />);
    expect(screen.getByText(/Dauer der Anfechtungsfrist ist nicht festgelegt/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Prüfdatum/), "2026-11-30");
    await userEvent.click(screen.getByRole("button", { name: "Prüfdatum als Frist anlegen" }));
    expect(await screen.findByTestId("deadline-created")).toHaveTextContent("30.11.2026");
    const init = f.mock.calls[0]![1] as RequestInit;
    expect(f.mock.calls[0]![0]).toBe(`/api/bff/hoa/resolutions/${ID}/review-deadline`);
    expect(JSON.parse(init.body as string)).toMatchObject({ due_on: "2026-11-30", note: null });
  });

  it("shows the API error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Nicht gefunden", status: 404 }, 404));
    renderIntl(<ResolutionFollowUps resolutionId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Folgen prüfen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
