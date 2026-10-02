import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

import { WorkOrderStepForm } from "./WorkOrderStepForm";

describe("WorkOrderStepForm (GAI-416)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers only the permitted follow-up steps and posts a quote", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ status: "quoted" }));
    renderIntl(<WorkOrderStepForm orderId="01920000-0000-7000-8000-0000000a1701" status="requested" canEdit />);
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Angebot erfasst", "Freigegeben", "Abgelehnt", "Storniert"]);
    await userEvent.type(screen.getByLabelText("Angebotsbetrag in EUR"), "1234,50");
    await userEvent.click(screen.getByRole("button", { name: "Schritt speichern" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Schritt gespeichert: Angebot erfasst");
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe("/api/bff/work-orders/01920000-0000-7000-8000-0000000a1701/steps");
    expect(JSON.parse(String(init?.body))).toEqual({ status: "quoted", quote_amount: "1234.50" });
    expect(screen.getByTestId("order-step-current")).toHaveTextContent("Angebot erfasst");
  });

  it("shows the API conflict and hides the form without the right", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Konflikt", detail: "Schritt nicht zulässig.", status: 409 }, 409));
    renderIntl(<WorkOrderStepForm orderId="01920000-0000-7000-8000-0000000a1701" status="approved" canEdit />);
    await userEvent.click(screen.getByRole("button", { name: "Schritt speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByTestId("order-step-current")).toHaveTextContent("Freigegeben");
  });

  it("offers no step for a final status or without the right", () => {
    renderIntl(<WorkOrderStepForm orderId="01920000-0000-7000-8000-0000000a1701" status="accepted" canEdit />);
    expect(screen.queryByRole("button", { name: "Schritt speichern" })).toBeNull();
  });
});
