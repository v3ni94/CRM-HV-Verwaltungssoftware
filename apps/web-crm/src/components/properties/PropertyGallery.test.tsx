import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyGallery } from "./PropertyGallery";

const PID = "11111111-1111-7111-8111-111111111111";
const D1 = "0192abcd-0000-7000-8000-000000000101";
const D2 = "0192abcd-0000-7000-8000-000000000102";
const D3 = "0192abcd-0000-7000-8000-000000000103";

describe("PropertyGallery", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the images in order and hides the controls without update right", () => {
    renderIntl(<PropertyGallery propertyId={PID} version={3} images={[D1, D2]} canEdit={false} />);
    const items = screen.getByTestId("property-image-list").querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0]?.querySelector("img")).toHaveAttribute("src", `/api/handover-files/documents/${D1}/content`);
    expect(items[1]).toHaveTextContent("Position 2");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("property-image-file")).not.toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderIntl(<PropertyGallery propertyId={PID} version={1} images={[]} canEdit />);
    expect(screen.getByText("Noch keine Bilder am Objekt.")).toBeInTheDocument();
  });

  it("uploads the file as a document linked to the property and appends it with If-Match", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ id: D3 }, 201))
      .mockResolvedValueOnce(jsonResponse({ version: 4, images: [D1, D3] }));
    renderIntl(<PropertyGallery propertyId={PID} version={3} images={[D1]} canEdit />);
    const file = new File([new Uint8Array([137, 80, 78, 71])], "fassade.png", { type: "image/png" });
    await userEvent.upload(screen.getByTestId("property-image-file"), file);
    await waitFor(() => expect(screen.getByTestId("property-image-list").querySelectorAll("li")).toHaveLength(2));
    const [uploadUrl, uploadInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(uploadUrl).toBe("/api/bff/documents");
    const form = uploadInit.body as FormData;
    expect(JSON.parse(String(form.get("links")))).toEqual([{ entity_type: "property", entity_id: PID, role: "attachment" }]);
    const [patchUrl, patchInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(patchUrl).toBe(`/api/bff/properties/${PID}`);
    expect(patchInit.method).toBe("PATCH");
    expect(new Headers(patchInit.headers).get("if-match")).toBe("3");
    expect(JSON.parse(String(patchInit.body))).toEqual({ images: [D1, D3] });
  });

  it("moves an image down and uses the new version for the next change", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ version: 4, images: [D2, D1] }))
      .mockResolvedValueOnce(jsonResponse({ version: 5, images: [D2] }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<PropertyGallery propertyId={PID} version={3} images={[D1, D2]} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Bild 1 nach hinten" }));
    await waitFor(() => expect(screen.getAllByRole("img")[0]).toHaveAttribute("src", expect.stringContaining(D2)));
    expect(JSON.parse(String((fetchMock.mock.calls[0] as [string, RequestInit])[1].body))).toEqual({ images: [D2, D1] });
    fireEvent.click(screen.getByRole("button", { name: "Bild 2 aus der Galerie entfernen" }));
    await waitFor(() => expect(screen.getByTestId("property-image-list").querySelectorAll("li")).toHaveLength(1));
    const second = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(new Headers(second[1].headers).get("if-match")).toBe("4");
    expect(JSON.parse(String(second[1].body))).toEqual({ images: [D2] });
  });

  it("tells the user to reload when the record changed in the meantime", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ title: "Vorbedingung", status: 412, detail: "Version veraltet" }, 412),
    );
    renderIntl(<PropertyGallery propertyId={PID} version={3} images={[D1, D2]} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Bild 1 nach hinten" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Das Objekt wurde zwischenzeitlich geändert");
    expect(screen.getAllByRole("img")[0]).toHaveAttribute("src", expect.stringContaining(D1));
  });
});
