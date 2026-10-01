import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DeadlineExceptionPanel } from "./DeadlineExceptionPanel";

const ID = "0192abcd-0000-7000-8000-000000000031";
const DOC = "0192abcd-0000-7000-8000-000000000032";
const EMPTY = {
  deadline_exception: null,
  deadline_exception_document_id: null,
  deadline_exception_set_at: null,
  deadline_exception_effective: false,
};

describe("DeadlineExceptionPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the lock and saves reason with evidence document", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        deadline_exception: "Verzögerung Messdienst",
        deadline_exception_document_id: DOC,
        deadline_exception_set_at: "2026-10-01T08:00:00Z",
        deadline_exception_effective: true,
      }),
    );
    renderIntl(<DeadlineExceptionPanel id={ID} status="draft" initial={EMPTY} />);
    expect(screen.getByText(/Nachforderung nach Fristablauf gesperrt/)).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Ausnahme speichern" });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Ausnahmegrund"), "Verzögerung Messdienst");
    await userEvent.type(screen.getByLabelText("Nachweisdokument (Dokument-ID)"), "kein-uuid");
    expect(save).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Nachweisdokument (Dokument-ID)"));
    await userEvent.type(screen.getByLabelText("Nachweisdokument (Dokument-ID)"), DOC);
    await userEvent.click(save);
    await waitFor(() => expect(screen.getByText("Ausnahme mit Nachweis hinterlegt")).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/statements/${ID}`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ deadline_exception: "Verzögerung Messdienst", deadline_exception_document_id: DOC });
  });

  it("is read only outside the draft", () => {
    renderIntl(<DeadlineExceptionPanel id={ID} status="calculated" initial={EMPTY} />);
    expect(screen.queryByRole("button", { name: "Ausnahme speichern" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ausnahmegrund")).toBeDisabled();
  });
});
