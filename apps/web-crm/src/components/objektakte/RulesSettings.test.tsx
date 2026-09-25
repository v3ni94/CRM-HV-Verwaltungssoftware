import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RulesSettings, type CategoryOption, type ClassificationRule } from "./RulesSettings";

const category: CategoryOption = { id: "cat-1", code: "01", name: "Stammakte" };

const rule: ClassificationRule = {
  id: "rule-1",
  name: "Verwalterbestellung",
  pattern_type: "text_keyword",
  pattern_value: "bestellung (des|zum|zur) verwalt",
  target_category_id: "cat-1",
  target_document_type: "verwalterbestellung",
  priority: 200,
  active: true,
  confidence: 0.9,
};

describe("RulesSettings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists an existing rule and creates a new one", async () => {
    const created: ClassificationRule = {
      id: "rule-2",
      name: "Neue Regel",
      pattern_type: "filename_regex",
      pattern_value: "forderung",
      target_category_id: null,
      target_document_type: null,
      priority: 100,
      active: true,
      confidence: 0.8,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(created)) // create
      .mockResolvedValueOnce(jsonResponse([rule, created])); // reload
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<RulesSettings initial={[rule]} categories={[category]} />);

    expect(screen.getByText("Verwalterbestellung")).toBeInTheDocument();

    await act(async () => {
      await userEvent.type(screen.getByLabelText("Name"), "Neue Regel");
      await userEvent.type(screen.getByLabelText("Muster"), "forderung");
      await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));
    });

    expect(screen.getAllByText("Neue Regel").length).toBeGreaterThan(0);
    const createCall = fetchMock.mock.calls[0];
    expect(String(createCall?.[0])).toContain("/objektakte/classification-rules");
    const body = JSON.parse(String(createCall?.[1]?.body));
    expect(body.name).toBe("Neue Regel");
    expect(body.pattern_value).toBe("forderung");
  });

  it("deactivates an existing rule", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ...rule, active: false })) // patch
      .mockResolvedValueOnce(jsonResponse([{ ...rule, active: false }])); // reload
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<RulesSettings initial={[rule]} categories={[category]} />);

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Deaktivieren" }));
    });

    const patchCall = fetchMock.mock.calls[0];
    expect(patchCall?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({ active: false });
  });
});
