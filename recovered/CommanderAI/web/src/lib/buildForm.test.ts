import {
  colorsParam,
  defaultForm,
  formFromBuildParams,
  formFromSearch,
  formProblem,
  formToRequest,
  formToSearch,
  rebuildHref,
} from "./buildForm";

describe("build form", () => {
  it("defaults: choose-commander mode, 37 lands, deterministic", () => {
    expect(formFromSearch(new URLSearchParams(), "builtin:expanded")).toEqual(
      defaultForm("builtin:expanded"),
    );
  });

  it("round-trips through the URL", () => {
    const form = {
      ...defaultForm("stored:3"),
      commander: "Alpha Partner",
      partner: "Beta Partner",
      theme: "tokens",
      lands: 35,
      variety: 0.6,
      seed: 42,
      budget: 75.5,
      bracket: 2,
    };
    expect(formFromSearch(formToSearch(form), "ignored")).toEqual(form);
    const auto = {
      ...defaultForm("builtin:expanded"),
      mode: "auto" as const,
      colors: ["U", "G"],
      theme: "ramp",
    };
    expect(formFromSearch(formToSearch(auto), "x")).toEqual(auto);
  });

  it("infers auto mode from theme/colors without a commander", () => {
    expect(formFromSearch(new URLSearchParams("theme=dragons"), "c").mode).toBe("auto");
    expect(formFromSearch(new URLSearchParams("colors=colorless"), "c").colors).toEqual(["C"]);
  });

  it("keeps manual mode when a theme is picked before the commander", () => {
    const form = { ...defaultForm("default"), theme: "tokens" };
    const restored = formFromSearch(formToSearch(form), "default");
    expect(restored.mode).toBe("commander");
    expect(formProblem(restored)).toBe("Choose a commander.");
  });

  it("can leave auto-pick while retaining its theme", () => {
    const auto = formFromSearch(new URLSearchParams("mode=auto&theme=tokens"), "default");
    const manual = formFromSearch(formToSearch({ ...auto, mode: "commander" }), "default");
    expect(manual.mode).toBe("commander");
    expect(manual.theme).toBe("tokens");
  });

  it("honors explicit manual mode over inferred auto-pick parameters", () => {
    expect(
      formFromSearch(new URLSearchParams("mode=commander&theme=tokens&colors=UG"), "default").mode,
    ).toBe("commander");
  });

  it("clamps or ignores invalid values", () => {
    const f = formFromSearch(new URLSearchParams("lands=500&variety=3&bracket=9&seed=abc"), "c");
    expect([f.lands, f.variety, f.bracket, f.seed]).toEqual([37, 1, null, null]);
  });

  it("explains what is missing", () => {
    expect(formProblem(defaultForm("c"))).toBe("Choose a commander.");
    expect(formProblem({ ...defaultForm("c"), mode: "auto" })).toMatch(/theme and\/or colors/);
    expect(formProblem({ ...defaultForm("c"), mode: "auto", colors: ["R"] })).toBeNull();
  });

  it("sends only the fields of the chosen mode", () => {
    const commander = formToRequest({
      ...defaultForm("c"),
      commander: "Z",
      colors: ["U"],
      theme: "tokens",
    });
    expect(commander).toMatchObject({ commander: "Z", colors: null, theme: "tokens" });
    const auto = formToRequest({
      ...defaultForm("c"),
      mode: "auto",
      commander: "Z",
      colors: ["G", "U"],
    });
    expect(auto).toMatchObject({ commander: null, partner: null, colors: "UG" });
  });

  it("formats colors for the API", () => {
    expect(colorsParam([])).toBeNull();
    expect(colorsParam(["G", "U", "C"])).toBe("UG");
    expect(colorsParam(["C"])).toBe("colorless");
  });

  it("builds a rebuild link from saved parameters", () => {
    const href = rebuildHref({
      collection: "builtin:expanded",
      commander: "Kardur, Doomscourge",
      partner: null,
      theme: null,
      colors: null,
      lands: 37,
      variety: 0,
      seed: 3,
      budget: null,
      bracket: null,
    });
    expect(href).toBe(
      "/build?collection=builtin%3Aexpanded&commander=Kardur%2C+Doomscourge&seed=3&run=1",
    );
  });

  it("restores all resolved build settings for a reproducible request", () => {
    for (const commander of [null, "Zaxara, the Exemplary"]) {
      const params = {
        collection: "stored:2",
        commander,
        partner: commander ? "Partner" : null,
        theme: "tokens",
        colors: commander ? null : "colorless",
        lands: 35,
        variety: 0.7,
        seed: 42,
        budget: 80,
        bracket: 3,
      };
      expect(formToRequest(formFromBuildParams(params))).toEqual(params);
    }
  });
});
