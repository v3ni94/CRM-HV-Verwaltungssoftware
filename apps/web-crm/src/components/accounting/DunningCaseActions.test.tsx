import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningCaseActions } from "./DunningCaseActions";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("DunningCaseActions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows mark-sent only for a proposed case", () => {
    renderIntl(<DunningCaseActions caseId="0192abcd-0000-7000-8000-000000000010" status="sent" isHighestLevel={false} />);
    expect(screen.queryByText("Als versendet markieren")).not.toBeInTheDocument();
  });

  it("marks a case as sent and refreshes the page", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ status: "sent" }));
    renderIntl(<DunningCaseActions caseId="0192abcd-0000-7000-8000-000000000010" status="proposed" isHighestLevel={false} />);
    await userEvent.click(screen.getByText("Als versendet markieren"));
    expect(refresh).toHaveBeenCalled();
  });

  it("only offers the Mahnbescheid action on the highest level", () => {
    renderIntl(<DunningCaseActions caseId="0192abcd-0000-7000-8000-000000000010" status="proposed" isHighestLevel={false} />);
    expect(screen.queryByText("Mahnbescheid vorbereiten")).not.toBeInTheDocument();
  });

  it("prepares a Mahnbescheid on the highest level and offers the JSON download", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        id: "0192abcd-0000-7000-8000-000000000099",
        case_id: "0192abcd-0000-7000-8000-000000000010",
        hauptforderung: "350.00",
        nebenforderungen: [],
        status: "in_vorbereitung",
        hinweis: "Vorbereitung, Prüfung durch Rechtsanwalt.",
      }),
    );
    renderIntl(<DunningCaseActions caseId="0192abcd-0000-7000-8000-000000000010" status="sent" isHighestLevel />);
    await userEvent.click(screen.getByText("Mahnbescheid vorbereiten"));
    expect(await screen.findByText("Vorbereitung herunterladen (JSON)")).toBeInTheDocument();
  });

  it("offers the PDF of the preparation once it exists and files it as a document", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          id: "0192abcd-0000-7000-8000-000000000099",
          case_id: "0192abcd-0000-7000-8000-000000000010",
          hauptforderung: "350.00",
          nebenforderungen: [],
          status: "in_vorbereitung",
          hinweis: "Vorbereitung, Prüfung durch Rechtsanwalt.",
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ document_id: "0192abcd-0000-7000-8000-000000000077" }, 201));
    renderIntl(<DunningCaseActions caseId="0192abcd-0000-7000-8000-000000000010" status="sent" isHighestLevel />);
    expect(screen.queryByText("Vorbereitung als PDF (kein Antrag)")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Mahnbescheid vorbereiten"));
    expect(await screen.findByText("Vorbereitung als PDF (kein Antrag)")).toBeInTheDocument();
    await userEvent.click(screen.getByText("PDF ablegen"));
    expect(await screen.findByText("PDF abgelegt")).toBeInTheDocument();
    expect(String(fetchSpy.mock.calls[1]?.[0])).toBe(
      "/api/bff/accounting/dunning-cases/0192abcd-0000-7000-8000-000000000010/mahnbescheid",
    );
  });
});
