import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Proposal } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { ASSISTANT_OPEN_EVENT, AssistantTab } from "./AssistantTab";
import { ChatActionProposal } from "./ChatActionProposal";

describe("AssistantTab (M7-05)", () => {
  it("lists the prepared actions of a contact and opens the assistant", async () => {
    const listener = vi.fn();
    window.addEventListener(ASSISTANT_OPEN_EVENT, listener);
    renderIntl(<AssistantTab kind="contact" />);
    expect(screen.getByText("Portaleinladung vorbereiten")).toBeInTheDocument();
    expect(screen.getByText(/erst nach Ihrer Bestätigung/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Assistent öffnen" }));
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(ASSISTANT_OPEN_EVENT, listener);
  });

  it("shows the property actions", () => {
    renderIntl(<AssistantTab kind="property" />);
    expect(screen.getByText("Dokument ablegen und verknüpfen")).toBeInTheDocument();
  });
});

const base = {
  id: "01920000-0000-7000-8000-00000000b010",
  task_run_id: "01920000-0000-7000-8000-00000000a010",
  entity_type: "chat_action",
  context_id: null,
  decision: "pending",
  decided_by: null,
  decided_at: null,
  import_run_id: null,
};

describe("ChatActionProposal M7-03 kinds", () => {
  it("shows a property proposal and the next steps after confirmation", async () => {
    const proposal = {
      ...base,
      proposed: { kind: "property_create", number: "894", name: "Eichenhof", management_type: "hoa", city: "Monheim", postal_code: "40789" },
    } as unknown as Proposal;
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: "x",
        summary: {
          kind: "property_create",
          property_id: "01920000-0000-7000-8000-00000000f00d",
          next_steps: [{ code: "units", label: "Einheiten und Gebäude prüfen oder anlegen", href: "/objekte/1" }],
        },
        items: [],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<ChatActionProposal proposal={proposal} />);
    expect(screen.getByText("Vorschlag: Objekt anlegen")).toBeInTheDocument();
    expect(screen.getByText("Objekt 894 Eichenhof")).toBeInTheDocument();
    expect(screen.getByText("WEG-Verwaltung")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen und übernehmen" }));
    expect(await screen.findByText("Einheiten und Gebäude prüfen oder anlegen")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("says that a portal invitation and a letter are not sent", () => {
    const invite = { ...base, proposed: { kind: "portal_invite_prepare", contact_label: "Kowalski, Jan", email_masked: "j***@example.org" } } as unknown as Proposal;
    renderIntl(<ChatActionProposal proposal={invite} />);
    expect(screen.getByText("E-Mail-Adresse aus der Kontaktakte: j***@example.org")).toBeInTheDocument();
    expect(screen.getByText(/Es wird nichts versendet/)).toBeInTheDocument();
    const letter = { ...base, id: "01920000-0000-7000-8000-00000000b011", proposed: { kind: "letter_create", template_label: "Begrüßung" } } as unknown as Proposal;
    renderIntl(<ChatActionProposal proposal={letter} />);
    expect(screen.getByText("Vorlage: Begrüßung")).toBeInTheDocument();
    expect(screen.getByText("Der Brief wird als Entwurf abgelegt und nicht versendet.")).toBeInTheDocument();
  });
});

describe("RentIncreaseAiCheck (M26-01)", () => {
  it("starts the check and shows hints with severity", async () => {
    const { RentIncreaseAiCheck } = await import("@/components/letting/RentIncreaseAiCheck");
    const state = {
      ai_check_id: "p",
      latest_run: { id: "r", status: "succeeded", error: null },
      latest: { id: "p", proposed: { findings: [{ field: "source_missing", description: "Quelle fehlt.", severity: "medium" }], overall: "pruefen", summary: "" } },
    };
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ ai_check_id: null, latest_run: null, latest: null })).mockResolvedValueOnce(jsonResponse(state));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<RentIncreaseAiCheck caseId="01920000-0000-7000-8000-00000000e001" canStart />);
    await userEvent.click(await screen.findByRole("button", { name: "KI-Prüfung starten" }));
    expect(await screen.findByText("Quelle fehlt.")).toBeInTheDocument();
    expect(screen.getByText("Gesamt: prüfen")).toBeInTheDocument();
    expect(screen.getByText("mittel")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
