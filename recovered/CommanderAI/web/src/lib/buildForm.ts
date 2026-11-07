// Build page form ⇄ URL ⇄ API request. Pure functions (unit tested).
import type { BuildParams, ResolvedBuildParams } from "../api/types";
import { WUBRG } from "./colors";

export type BuildMode = "commander" | "auto";

export interface BuildForm {
  collection: string;
  mode: BuildMode;
  commander: string | null;
  partner: string | null;
  theme: string | null;
  colors: string[]; // WUBRG letters and/or "C"
  lands: number;
  variety: number;
  seed: number | null;
  budget: number | null;
  bracket: number | null;
}

export const DEFAULT_LANDS = 37;

export function defaultForm(collection: string): BuildForm {
  return {
    collection,
    mode: "commander",
    commander: null,
    partner: null,
    theme: null,
    colors: [],
    lands: DEFAULT_LANDS,
    variety: 0,
    seed: null,
    budget: null,
    bracket: null,
  };
}

const num = (v: string | null): number | null =>
  v !== null && v !== "" && Number.isFinite(Number(v)) ? Number(v) : null;

/** Colors for the API: "UG", or "colorless" when only C is selected. */
export function colorsParam(colors: string[]): string | null {
  if (colors.length === 0) return null;
  return WUBRG.filter((c) => colors.includes(c)).join("") || "colorless";
}

export function formFromSearch(p: URLSearchParams, fallbackCollection: string): BuildForm {
  const colors = (p.get("colors") ?? "").toUpperCase();
  const commander = p.get("commander");
  const explicitMode = p.get("mode");
  const mode: BuildMode =
    explicitMode === "commander" || explicitMode === "auto"
      ? explicitMode
      : !commander && (p.get("theme") || colors)
        ? "auto"
        : "commander";
  const lands = num(p.get("lands"));
  const variety = num(p.get("variety"));
  const bracket = num(p.get("bracket"));
  return {
    collection: p.get("collection") || fallbackCollection,
    mode,
    commander: mode === "commander" ? commander : null,
    partner: mode === "commander" ? p.get("partner") : null,
    theme: p.get("theme"),
    colors: colors === "COLORLESS" ? ["C"] : [...WUBRG, "C"].filter((c) => colors.includes(c)),
    lands: lands !== null && lands >= 0 && lands <= 99 ? Math.round(lands) : DEFAULT_LANDS,
    variety: variety !== null ? Math.min(1, Math.max(0, variety)) : 0,
    seed: num(p.get("seed")),
    budget: num(p.get("budget")),
    bracket: bracket !== null && bracket >= 1 && bracket <= 5 ? bracket : null,
  };
}

export function formToSearch(f: BuildForm): URLSearchParams {
  const p = new URLSearchParams();
  p.set("collection", f.collection);
  if (f.mode === "auto") p.set("mode", "auto");
  // A theme without a commander otherwise looks like an implicit auto-pick link.
  if (f.mode === "commander" && !f.commander && f.theme) p.set("mode", "commander");
  if (f.mode === "commander" && f.commander) p.set("commander", f.commander);
  if (f.mode === "commander" && f.partner) p.set("partner", f.partner);
  if (f.theme) p.set("theme", f.theme);
  const colors = colorsParam(f.colors);
  if (f.mode === "auto" && colors) p.set("colors", colors);
  if (f.lands !== DEFAULT_LANDS) p.set("lands", String(f.lands));
  if (f.variety > 0) p.set("variety", String(f.variety));
  if (f.seed !== null) p.set("seed", String(f.seed));
  if (f.budget !== null) p.set("budget", String(f.budget));
  if (f.bracket !== null) p.set("bracket", String(f.bracket));
  return p;
}

/** What's missing before the form can be built, or null when it's ready. */
export function formProblem(f: BuildForm): string | null {
  if (f.mode === "commander" && !f.commander) return "Choose a commander.";
  if (f.mode === "auto" && !f.theme && f.colors.length === 0)
    return "Pick a theme and/or colors — CommanderAI then chooses the best commander you own.";
  return null;
}

export function formToRequest(f: BuildForm): BuildParams {
  const commanderMode = f.mode === "commander";
  return {
    collection: f.collection,
    commander: commanderMode ? f.commander : null,
    partner: commanderMode ? f.partner : null,
    theme: f.theme,
    colors: commanderMode ? null : colorsParam(f.colors),
    lands: f.lands,
    variety: f.variety,
    seed: f.seed,
    budget: f.budget,
    bracket: f.bracket,
  };
}

/** Restore every setting from a completed build, independently of current edits. */
export function formFromBuildParams(params: ResolvedBuildParams): BuildForm {
  return {
    collection: params.collection,
    mode: params.commander ? "commander" : "auto",
    commander: params.commander,
    partner: params.partner,
    theme: params.theme,
    colors: params.colors
      ? params.colors === "colorless"
        ? ["C"]
        : params.colors.toUpperCase().split("")
      : [],
    lands: params.lands,
    variety: params.variety,
    seed: params.seed,
    budget: params.budget,
    bracket: params.bracket,
  };
}

/** Build page URL that repeats a build (e.g. from a saved deck's parameters). */
export function rebuildHref(params: ResolvedBuildParams, run = true): string {
  const search = formToSearch(formFromBuildParams(params));
  if (run) search.set("run", "1");
  return `/build?${search}`;
}
