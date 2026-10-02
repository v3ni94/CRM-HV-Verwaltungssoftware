import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ExportKinds } from "./ExportKinds";

describe("ExportKinds (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the kinds with required columns marked", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([{ kind: "owners", label: "Eigentümer", columns: ["name", "email"], required: ["name"], reconciled: true }]),
    );
    renderIntl(<ExportKinds />);
    expect(await screen.findByText("Eigentümer")).toBeInTheDocument();
    expect(screen.getByText("name *, email")).toBeInTheDocument();
    expect(screen.getByText("(owners, wird abgeglichen)")).toBeInTheDocument();
  });

  it("shows the error of the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Fehler", status: 500 }, 500));
    renderIntl(<ExportKinds />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
