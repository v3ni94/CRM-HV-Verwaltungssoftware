import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DocumentVisibilityEditor } from "./DocumentVisibilityEditor";

describe("DocumentVisibilityEditor", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("saves the chosen roles and 'internal' when none is chosen", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async () => jsonResponse({ id: "d1", visibility: ["owner"] }));
    renderIntl(<DocumentVisibilityEditor documentId="d1" visibility={["tenant"]} canEdit />);
    expect(screen.getByTestId("visibility-current")).toHaveTextContent("Mieter");
    await user.click(screen.getByLabelText("Eigentümer"));
    await user.click(screen.getByLabelText("Mieter"));
    await user.click(screen.getByRole("button", { name: "Sichtbarkeit speichern" }));
    await waitFor(() => expect(screen.getByTestId("visibility-current")).toHaveTextContent("Eigentümer"));
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toEqual({ visibility: ["owner"] });
    await user.click(screen.getByLabelText("nur intern"));
    await user.click(screen.getByRole("button", { name: "Sichtbarkeit speichern" }));
    await waitFor(() => expect(screen.getByTestId("visibility-current")).toHaveTextContent("nur intern"));
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual({ visibility: ["internal"] });
  });

  it("is read only without the permission", () => {
    renderIntl(<DocumentVisibilityEditor documentId="d1" visibility={["internal"]} canEdit={false} />);
    expect(screen.getByText("nur intern")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
