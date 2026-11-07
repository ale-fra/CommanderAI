import { MantineProvider } from "@mantine/core";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { CollectionSelect } from "./CollectionSelect";

const setId = vi.hoisted(() => vi.fn());
vi.mock("../state/ActiveCollection", () => ({
  useActiveCollection: () => ({
    id: "default",
    setId,
    collections: [
      { id: "default", kind: "default", name: "Original", copies: 100 },
      { id: "stored:2", kind: "stored", name: "Second", copies: 120 },
    ],
  }),
}));

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

describe("active collection selection", () => {
  beforeEach(() => {
    setId.mockClear();
    vi.stubGlobal("matchMedia", () => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const renderAt = (path: string) =>
    render(
      <MantineProvider env="test">
        <MemoryRouter initialEntries={[path]}>
          <CollectionSelect />
          <Location />
        </MemoryRouter>
      </MantineProvider>,
    );

  it("switches the build collection and clears commander, partner and auto-run", async () => {
    renderAt(
      "/build?collection=default&commander=Zaxara&partner=Partner&theme=tokens&lands=35&run=1",
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: "Active collection" }));
    await user.click(screen.getByRole("option", { name: "Second (120)" }));
    expect(setId).toHaveBeenCalledWith("stored:2");
    const url = new URL(screen.getByTestId("location").textContent ?? "", "http://localhost");
    expect(url.searchParams.get("collection")).toBe("stored:2");
    expect(url.searchParams.get("mode")).toBe("commander");
    expect(url.searchParams.get("theme")).toBe("tokens");
    expect(url.searchParams.get("lands")).toBe("35");
    for (const key of ["commander", "partner", "run"])
      expect(url.searchParams.has(key)).toBe(false);
  });

  it("keeps the current route and filters when selecting elsewhere", async () => {
    renderAt("/collection?c=UG&q=draw");
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: "Active collection" }));
    await user.click(screen.getByRole("option", { name: "Second (120)" }));
    expect(setId).toHaveBeenCalledWith("stored:2");
    expect(screen.getByTestId("location")).toHaveTextContent("/collection?c=UG&q=draw");
  });
});
