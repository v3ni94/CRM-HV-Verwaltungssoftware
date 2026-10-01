import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactTagsAdmin, type ContactTag } from "./ContactTagsAdmin";

const A: ContactTag = { id: "11111111-1111-7111-8111-111111111111", name: "Beirat", contacts: 4 };
const B: ContactTag = { id: "22222222-2222-7222-8222-222222222222", name: "Beiräte", contacts: 1 };

describe("ContactTagsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the tags with their usage", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([A, B]));
    renderIntl(<ContactTagsAdmin canUpdate canDelete />);
    const rows = await screen.findAllByTestId("contact-tag-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Beirat");
    expect(rows[0]).toHaveTextContent("4");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/contact-tags");
  });

  it("offers no change actions without permissions", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([A]));
    renderIntl(<ContactTagsAdmin canUpdate={false} canDelete={false} />);
    await screen.findByTestId("contact-tag-row");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renames a tag and reloads the list", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([A]))
      .mockResolvedValueOnce(jsonResponse({ ...A, name: "Verwaltungsbeirat" }))
      .mockResolvedValueOnce(jsonResponse([{ ...A, name: "Verwaltungsbeirat" }]));
    renderIntl(<ContactTagsAdmin canUpdate canDelete />);
    await screen.findByTestId("contact-tag-row");
    fireEvent.click(screen.getByRole("button", { name: "Tag Beirat umbenennen" }));
    fireEvent.change(screen.getByLabelText("Neuer Name für Beirat"), { target: { value: "Verwaltungsbeirat" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await screen.findByText("Verwaltungsbeirat");
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contact-tags/${A.id}`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ name: "Verwaltungsbeirat" });
  });

  it("shows the conflict message of the API when the name exists", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([A, B]))
      .mockResolvedValueOnce(
        jsonResponse({ title: "Konflikt", status: 409, detail: "Ein Tag mit diesem Namen existiert bereits, bitte zusammenführen." }, 409),
      );
    renderIntl(<ContactTagsAdmin canUpdate canDelete />);
    await screen.findAllByTestId("contact-tag-row");
    fireEvent.click(screen.getByRole("button", { name: "Tag Beirat umbenennen" }));
    fireEvent.change(screen.getByLabelText("Neuer Name für Beirat"), { target: { value: "Beiräte" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("bitte zusammenführen");
  });

  it("merges a tag into the chosen target after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([A, B]))
      .mockResolvedValueOnce(jsonResponse({ ...A, contacts: 5 }))
      .mockResolvedValueOnce(jsonResponse([{ ...A, contacts: 5 }]));
    renderIntl(<ContactTagsAdmin canUpdate canDelete />);
    await screen.findAllByTestId("contact-tag-row");
    fireEvent.click(screen.getByRole("button", { name: "Tag Beiräte zusammenführen" }));
    fireEvent.change(screen.getByLabelText("Zieltag für Beiräte"), { target: { value: A.id } });
    fireEvent.click(screen.getByRole("button", { name: "Zusammenführen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contact-tags/${B.id}/merge`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ target_id: A.id });
  });

  it("deletes a tag only after confirmation", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([A]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<ContactTagsAdmin canUpdate canDelete />);
    await screen.findByTestId("contact-tag-row");
    fireEvent.click(screen.getByRole("button", { name: "Tag Beirat löschen" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Tag Beirat löschen" }));
    await screen.findByText("Keine Tags vorhanden.");
    expect(confirm).toHaveBeenCalledTimes(2);
    expect((fetchMock.mock.calls[1] as [string, RequestInit])[1].method).toBe("DELETE");
  });
});
