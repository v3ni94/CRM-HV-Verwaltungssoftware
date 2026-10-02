import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ResultEntriesPanel } from "./ResultEntriesPanel";
import { StatementInspectionsPanel } from "./StatementInspectionsPanel";

const ID = "0192abcd-0000-7000-8000-000000000011";

describe("StatementInspectionsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads on demand and records a request", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      return (init?.method ?? "GET") === "GET" ? jsonResponse([]) : jsonResponse({}, 201);
    });
    renderIntl(<StatementInspectionsPanel id={ID} contracts={[{ contract_id: "c1", unit_number: "WE 01" }]} />);
    expect(calls).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Anfragen laden" }));
    expect(await screen.findByText("Keine Anfragen erfasst.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Eingang am"), { target: { value: "2026-10-01" } });
    await userEvent.click(screen.getByRole("button", { name: "Anfrage erfassen" }));
    await waitFor(() => expect(calls).toContain(`POST /api/bff/statements/${ID}/inspections`));
  });
});

describe("ResultEntriesPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is offered only when due and shows the G3 refusal", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ title: "Freigabestufe", status: 403, detail: "Freigabestufe G3 ist nicht erteilt." }, 403),
    );
    const { unmount } = renderIntl(<ResultEntriesPanel id={ID} status="calculated" />);
    expect(screen.getByText("Ergebnisbuchungen sind erst im Status fällig möglich.")).toBeInTheDocument();
    unmount();
    renderIntl(<ResultEntriesPanel id={ID} status="due" />);
    const create = screen.getByRole("button", { name: "Entwürfe erzeugen" });
    expect(create).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Buchungsdatum"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Fälligkeit"), { target: { value: "2026-11-01" } });
    await userEvent.click(create);
    expect(await screen.findByRole("alert")).toHaveTextContent("Freigabestufe G3");
  });
});
