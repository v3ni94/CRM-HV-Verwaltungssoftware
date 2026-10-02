import { render } from "@testing-library/react";

import { PwaRegister } from "./PwaRegister";

describe("PwaRegister", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, "serviceWorker");
  });

  it("registers /sw.js with root scope and renders nothing", () => {
    const register = vi.fn().mockResolvedValue({});
    Object.defineProperty(navigator, "serviceWorker", { value: { register }, configurable: true });
    const { container } = render(<PwaRegister />);
    expect(register).toHaveBeenCalledWith("/sw.js", { scope: "/" });
    expect(container).toBeEmptyDOMElement();
  });

  it("does nothing where service workers are unavailable", () => {
    expect(() => render(<PwaRegister />)).not.toThrow();
  });

  it("ignores a failed registration", async () => {
    const register = vi.fn().mockRejectedValue(new Error("blocked"));
    Object.defineProperty(navigator, "serviceWorker", { value: { register }, configurable: true });
    render(<PwaRegister />);
    await Promise.resolve();
    expect(register).toHaveBeenCalledTimes(1);
  });
});
