import { MantineProvider } from "@mantine/core";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import BuildPage from "./BuildPage";

const controls = vi.hoisted(() => ({
  mutate: vi.fn(),
  reset: vi.fn(),
  setId: vi.fn(),
  collections: [{ id: "default" }, { id: "stored:2" }],
  params: {
    collection: "default",
    commander: "Zaxara, the Exemplary",
    partner: null,
    theme: null,
    colors: null,
    lands: 37,
    variety: 0,
    seed: 42,
    budget: null,
    bracket: null,
  },
}));

vi.mock("../state/ActiveCollection", () => ({
  useActiveCollection: () => ({
    id: "default",
    collections: controls.collections,
    setId: controls.setId,
  }),
}));
vi.mock("../components/CardDetail", () => ({ useCardDetail: () => vi.fn() }));
vi.mock("../components/CardImage", () => ({ CardImage: () => null }));
vi.mock("../components/DeckCardList", () => ({ DeckCardList: () => null }));
vi.mock("../components/DeckStatsPanel", () => ({ StatSummary: () => null }));
vi.mock("../api/queries", () => ({
  useBuild: () => ({
    mutate: controls.mutate,
    reset: controls.reset,
    isPending: false,
    data: {
      build_id: "preview",
      result: {
        params: controls.params,
        deck: { commander: { name: "Zaxara, the Exemplary", color_identity: ["U", "B", "G"] } },
        stats: {},
        tokens: [],
        report: {
          notices: [],
          autopick: { commander_auto: false },
          seed: 42,
          bracket: null,
          budget: null,
        },
      },
    },
  }),
  useCommanders: () => ({ data: [], isLoading: false }),
  usePartners: () => ({ data: [] }),
  useVocabulary: () => ({}),
  useStatus: () => ({}),
  useSaveBuild: () => ({}),
}));

describe("build page state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const renderAt = (path: string) =>
    render(
      <MantineProvider env="test">
        <MemoryRouter initialEntries={[path]}>
          <BuildPage />
        </MemoryRouter>
      </MantineProvider>,
    );

  it("rebuilds the displayed result with its settings after the form has been edited", () => {
    renderAt(
      "/build?collection=default&commander=Zaxara&lands=38&seed=7&theme=tokens&budget=20&bracket=2",
    );
    fireEvent.click(screen.getByRole("button", { name: "Rebuild" }));
    expect(controls.mutate).toHaveBeenCalledWith(controls.params, expect.any(Object));
  });

  it("selects the collection from a saved build link in the header", () => {
    renderAt("/build?collection=stored%3A2&commander=Zaxara");
    expect(controls.setId).toHaveBeenCalledWith("stored:2");
  });
});
