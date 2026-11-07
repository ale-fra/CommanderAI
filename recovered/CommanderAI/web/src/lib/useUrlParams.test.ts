import { patchParams } from "./useUrlParams";

describe("patchParams", () => {
  it("sets, replaces and deletes keys without touching the others", () => {
    const next = patchParams(new URLSearchParams("a=1&b=2&c=3"), {
      a: "9",
      b: null,
      d: "4",
      c: "",
    });
    expect(next.toString()).toBe("a=9&d=4");
  });
});
