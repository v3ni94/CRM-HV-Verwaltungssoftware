import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ConsumptionInfoDeliveryForm } from "./ConsumptionInfoDeliveryForm";

const P = "0192abcd-0000-7000-8000-0000000023a1";
const I = "0192abcd-0000-7000-8000-0000000023a2";

describe("ConsumptionInfoDeliveryForm (GAJ-103)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing without update permission", () => {
    const { container } = renderIntl(<ConsumptionInfoDeliveryForm propertyId={P} infoId={I} canUpdate={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("needs date and evidence and PUTs the delivery", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({}));
    const saved = vi.fn();
    renderIntl(<ConsumptionInfoDeliveryForm propertyId={P} infoId={I} canUpdate onSaved={saved} />);
    await userEvent.click(screen.getByRole("button", { name: "Zustellung erfassen" }));
    const save = screen.getByRole("button", { name: "Zustellung speichern" });
    expect(save).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Weg"), "email");
    await userEvent.type(screen.getByLabelText("Zugestellt am"), "2026-10-02");
    await userEvent.type(screen.getByLabelText("Nachweis"), "Sendebestätigung");
    await userEvent.click(save);
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/properties/${P}/consumption-info/${I}/delivery`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ channel: "email", delivered_on: "2026-10-02", evidence: "Sendebestätigung" });
    expect(screen.getByText("Zustellung gespeichert.")).toBeInTheDocument();
  });

  it("shows the problem of the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Konflikt", status: 409, detail: "Bereits erfasst." }, 409));
    renderIntl(<ConsumptionInfoDeliveryForm propertyId={P} infoId={I} canUpdate />);
    await userEvent.click(screen.getByRole("button", { name: "Zustellung erfassen" }));
    await userEvent.type(screen.getByLabelText("Zugestellt am"), "2026-10-02");
    await userEvent.type(screen.getByLabelText("Nachweis"), "Beleg");
    await userEvent.click(screen.getByRole("button", { name: "Zustellung speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
