import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AiLearningExamples } from "./AiLearningExamples";

describe("AiLearningExamples", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the switch off by default and patches the tenant setting", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ ai_learning_examples_enabled: JSON.parse(String(init.body)).ai_learning_examples_enabled });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<AiLearningExamples initial={false} canUpdate />);
    expect(screen.getByTestId("ai-learning-examples-status")).toHaveTextContent("aus");
    expect(screen.getByText(/Standard aus/)).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("checkbox"));

    await waitFor(() => expect(screen.getByTestId("ai-learning-examples-status")).toHaveTextContent("an"));
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ ai_learning_examples_enabled: true }) }),
    );
  });

  it("is read only without the update permission", () => {
    renderIntl(<AiLearningExamples initial={false} canUpdate={false} />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
  });

  it("shows the error when the change is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung." }, 403),
    );
    renderIntl(<AiLearningExamples initial={false} canUpdate />);
    await userEvent.setup().click(screen.getByRole("checkbox"));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByTestId("ai-learning-examples-status")).toHaveTextContent("aus");
  });
});
