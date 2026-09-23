import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RentIncreaseActions, RentIncreaseCreate } from "./RentIncreaseForms";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
const ID = "0192abcd-0000-7000-8000-000000000040";

describe("RentIncreaseCreate", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends entered values with decimal points and opens the case", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: ID }, 201));
    renderIntl(<RentIncreaseCreate contracts={[{ id: "c1", label: "MV-1" }]} />);
    await userEvent.type(screen.getByLabelText("Zielmiete netto"), "690,00");
    await userEvent.type(screen.getByLabelText("Wirksam ab"), "2026-12-01");
    await userEvent.type(screen.getByLabelText("Kappungsgrenze in %"), "15");
    await userEvent.click(screen.getByText("Anlegen und rechnerisch prüfen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/vermietung/mieterhoehung/${ID}`));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      contract_id: "c1",
      basis: "mietspiegel",
      target_rent: "690.00",
      effective_date: "2026-12-01",
      cap_limit_percent: "15",
    });
  });
});

describe("RentIncreaseActions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requires the review document before sending", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<RentIncreaseActions id={ID} status="approved" />);
    await userEvent.click(screen.getByText("Versand erfassen"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nachweis");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads the consent evidence, then records consent", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ id: "doc1" }, 201))
      .mockResolvedValueOnce(jsonResponse({ status: "consented" }));
    renderIntl(<RentIncreaseActions id={ID} status="sent" />);
    await userEvent.upload(screen.getByLabelText("Nachweis der Zustimmung"), new File(["x"], "ok.pdf", { type: "application/pdf" }));
    await userEvent.click(screen.getByText("Zustimmung erfassen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ action: "consent", document_id: "doc1" });
  });
});
