import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { api } from "./client";
import { useSuggestCommanders } from "./queries";

describe("commander suggestion requests", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([undefined, 42])("runs again with unchanged filters and seed %s", async (seed) => {
    const get = vi.spyOn(api, "GET").mockImplementation(async () => ({
      data: { suggestions: [], seed: seed ?? 123, variety: 0.7, theme: null },
      response: new Response(null, { status: 200 }),
    }));
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result, unmount } = renderHook(() => useSuggestCommanders(), { wrapper });
    const params = { collection: "default", variety: 0.7, ...(seed === undefined ? {} : { seed }) };
    await act(async () => {
      await result.current.mutateAsync(params);
    });
    await act(async () => {
      await result.current.mutateAsync(params);
    });
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenLastCalledWith("/api/commanders/suggestions", {
      params: { query: params },
    });
    unmount();
    client.clear();
  });
});
