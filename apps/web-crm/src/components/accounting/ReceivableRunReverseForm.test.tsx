import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReceivableRunReverseForm } from "./ReceivableRunReverseForm";

const RUN = "0192abcd-0000-7000-8000-0000000023b1";

describe("ReceivableRunReverseForm (GAJ-101)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is hidden without approval permission", () => {
    const { container } = renderIntl(<ReceivableRunReverseForm runId={RUN} canApprove={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("needs a reason, asks for confirmation and posts the reversal", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({}));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const done = vi.fn();
    renderIntl(<ReceivableRunReverseForm runId={RUN} canApprove onReversed={done} />);
    await userEvent.click(screen.getByRole("button", { name: "Lauf stornieren" }));
    const submit = screen.getByRole("button", { name: "Storno ausführen" });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Begründung"), "Falscher Monat");
    await userEvent.click(submit);
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/accounting/receivable-runs/${RUN}/reverse`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ reason: "Falscher Monat", booking_date: null });
    expect(screen.getByText("Lauf storniert.")).toBeInTheDocument();
  });

  it("does nothing when the confirmation is declined and shows API errors", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Konflikt", status: 409, detail: "Bereits storniert." }, 409));
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<ReceivableRunReverseForm runId={RUN} canApprove />);
    await userEvent.click(screen.getByRole("button", { name: "Lauf stornieren" }));
    await userEvent.type(screen.getByLabelText("Begründung"), "Grund");
    await userEvent.click(screen.getByRole("button", { name: "Storno ausführen" }));
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Storno ausführen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledTimes(2);
  });
});
