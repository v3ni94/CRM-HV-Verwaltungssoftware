import { screen } from "@testing-library/react";

import { parseRoleFilter } from "@/lib/contact-schema";
import { renderIntl } from "@/test/intl";

import { RolePills } from "./RolePills";

describe("parseRoleFilter", () => {
  it("accepts a known role code", () => {
    expect(parseRoleFilter("mieter")).toBe("mieter");
    expect(parseRoleFilter("eigentuemer")).toBe("eigentuemer");
  });

  it("rejects an unknown or missing role", () => {
    expect(parseRoleFilter("not-a-role")).toBeUndefined();
    expect(parseRoleFilter(undefined)).toBeUndefined();
    expect(parseRoleFilter("")).toBeUndefined();
  });
});

describe("RolePills", () => {
  it("renders a pill per role", () => {
    renderIntl(<RolePills roles={["mieter", "eigentuemer"]} />);
    expect(screen.getByText("Mieter")).toBeInTheDocument();
    expect(screen.getByText("Eigentümer")).toBeInTheDocument();
  });

  it("renders nothing without roles", () => {
    const { container } = renderIntl(<RolePills roles={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
