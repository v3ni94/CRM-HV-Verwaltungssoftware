import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReserveCreateForm, ReserveMovementForm } from "./ReserveForms";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const LEDGER = "0192abcd-0000-7000-8000-000000000501";
const STATEMENT = "0192abcd-0000-7000-8000-000000000502";
const DACH = "0192abcd-0000-7000-8000-000000000503";

describe("Reserve forms", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates an earmarked reserve", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: DACH }, 201));
    renderIntl(<ReserveCreateForm ledgerId={LEDGER} />);
    const submit = screen.getByRole("button", { name: "Anlegen" });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Dach");
    await userEvent.type(screen.getByLabelText("Zweck"), "Dachsanierung");
    await userEvent.click(submit);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/hoa/reserves");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ ledger_id: LEDGER, name: "Dach", purpose: "Dachsanierung" });
    expect(refresh).toHaveBeenCalled();
  });

  it("records a use of funds with a decimal comma as dot amount", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "m1" }, 201));
    renderIntl(<ReserveMovementForm statementId={STATEMENT} reserves={[{ id: DACH, name: "Dach" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Art"), "fee");
    await userEvent.type(screen.getByLabelText("Betrag"), "10,50");
    await userEvent.type(screen.getByLabelText("Zweck"), "Kontoführung");
    await userEvent.click(screen.getByRole("button", { name: "Erfassen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/statements/${STATEMENT}/reserve-movements`);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ reserve_id: DACH, kind: "fee", amount: "10.50", purpose: "Kontoführung" });
  });
});
