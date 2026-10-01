import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { NotificationMailContent } from "./NotificationMailContent";

describe("NotificationMailContent", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the default mode and patches the hint mode", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "PATCH") return jsonResponse({ notification_mail_content: JSON.parse(String(init.body)).notification_mail_content });
      return jsonResponse({ notification_mail_content: "voll" });
    });
    renderIntl(<NotificationMailContent />);
    const full = await screen.findByTestId("notification-mail-content-voll");
    expect(full).toBeChecked();
    await userEvent.setup().click(screen.getByTestId("notification-mail-content-hinweis"));
    await waitFor(() => expect(screen.getByTestId("notification-mail-content-hinweis")).toBeChecked());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ notification_mail_content: "hinweis" }) }),
    );
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
  });

  it("renders nothing without read access", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "verboten" }, 403));
    const { container } = renderIntl(<NotificationMailContent />);
    await waitFor(() => expect(fetchSpyCalled()).toBe(true));
    expect(container).toBeEmptyDOMElement();
  });
});

function fetchSpyCalled() {
  return (globalThis.fetch as unknown as { mock: { calls: unknown[] } }).mock.calls.length > 0;
}
