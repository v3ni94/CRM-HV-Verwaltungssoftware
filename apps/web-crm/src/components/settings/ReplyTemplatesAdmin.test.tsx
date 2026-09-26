import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReplyTemplatesAdmin } from "./ReplyTemplatesAdmin";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const TPL = "01920000-0000-7000-8000-0000000000e1";
const DOC = "01920000-0000-7000-8000-0000000000d1";

describe("ReplyTemplatesAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a template with topic and a document attachment", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/reply-templates/placeholders")) return jsonResponse(["anrede", "name", "objekt", "ticketnummer"]);
      if (url.endsWith("/tenant/competence-catalogue")) return jsonResponse([{ code: "vertrag", label: "Vertrag" }]);
      if (url.endsWith("/tickets/reply-templates") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({ id: TPL, ...body, active: true }, 201);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(
      <ReplyTemplatesAdmin
        initialTemplates={[]}
        canManage
        canPickTopic
        canSearchDocuments
        documentQuery="merk"
        documentHits={[{ id: DOC, title: "Merkblatt Heizung", filename: "merkblatt.pdf" }]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Neue Antwortvorlage" }));
    await userEvent.type(screen.getByLabelText("Name"), "Eingangsbestätigung");
    // Geschweifte Klammern sind in userEvent.type Steuerzeichen, daher Einfügen per paste.
    await userEvent.click(screen.getByLabelText("Betreff"));
    await userEvent.paste("Ticket {ticketnummer}");
    await userEvent.click(screen.getByLabelText("Text"));
    await userEvent.paste("{anrede}, danke.");
    await waitFor(() => expect(screen.getByRole("option", { name: "Vertrag" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Thema"), "vertrag");
    await userEvent.click(within(screen.getByTestId("reply-template-document-hits")).getByRole("button", { name: "Als Anhang übernehmen" }));
    expect(within(screen.getByTestId("reply-template-attachments")).getByText("Merkblatt Heizung")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByTestId("reply-templates")).toBeInTheDocument());
    const createCall = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      name: "Eingangsbestätigung",
      subject: "Ticket {ticketnummer}",
      body: "{anrede}, danke.",
      topic: "vertrag",
      attachment_document_ids: [DOC],
    });
    expect(screen.getByText("Eingangsbestätigung")).toBeInTheDocument();
    expect(screen.getByText("1 Anhang/Anhänge")).toBeInTheDocument();
  });

  it("searches documents through the page query and hides actions without permission", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<ReplyTemplatesAdmin initialTemplates={[]} canManage canPickTopic={false} canSearchDocuments documentQuery="" documentHits={null} />);
    await userEvent.click(screen.getByRole("button", { name: "Neue Antwortvorlage" }));
    await userEvent.type(screen.getByLabelText("Dokument suchen"), "merkblatt{enter}");
    expect(push).toHaveBeenCalledWith("/einstellungen/antwortvorlagen?q=merkblatt", { scroll: false });

    renderIntl(
      <ReplyTemplatesAdmin
        initialTemplates={[{ id: TPL, name: "Nur lesen", subject: "x", body: "y", topic: null, attachment_document_ids: [], active: true }]}
        canManage={false}
        canPickTopic={false}
        canSearchDocuments={false}
      />,
    );
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.getByText("Nur lesen")).toBeInTheDocument();
  });
});
