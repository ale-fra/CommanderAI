// TanStack Query hooks over the typed client. Query keys live in `keys` so that
// mutations invalidate precisely what they change.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { BuildParams } from "./types";

export const keys = {
  status: ["status"] as const,
  vocabulary: ["vocabulary"] as const,
  card: (name: string) => ["card", name] as const,
  collections: ["collections"] as const,
  collection: (id: string) => ["collections", id] as const,
  collectionCards: (id: string) => ["collections", id, "cards"] as const,
  commanders: (collection: string, colors?: string) =>
    ["commanders", collection, colors ?? ""] as const,
  partners: (collection: string, commander: string) => ["partners", collection, commander] as const,
  decks: ["decks"] as const,
  deckList: (params: object) => ["decks", "list", params] as const,
  deck: (id: number) => ["decks", id] as const,
};

const forever = { staleTime: Number.POSITIVE_INFINITY };

// --- system / cards -------------------------------------------------------------------

export function useStatus() {
  return useQuery({ queryKey: keys.status, queryFn: () => unwrap(api.GET("/api/status")) });
}

export function useVocabulary() {
  return useQuery({
    queryKey: keys.vocabulary,
    queryFn: () => unwrap(api.GET("/api/vocabulary")),
    ...forever,
  });
}

export function useCard(name: string | null) {
  return useQuery({
    queryKey: keys.card(name ?? ""),
    queryFn: () => unwrap(api.GET("/api/card", { params: { query: { name: name ?? "" } } })),
    enabled: Boolean(name),
    ...forever,
  });
}

// --- collections ----------------------------------------------------------------------

export function useCollections() {
  return useQuery({
    queryKey: keys.collections,
    queryFn: () => unwrap(api.GET("/api/collections")),
  });
}

export function useCollectionDetail(id: string | null) {
  return useQuery({
    queryKey: keys.collection(id ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/api/collections/{collection_id}", {
          params: { path: { collection_id: id ?? "" } },
        }),
      ),
    enabled: Boolean(id),
  });
}

export function useCollectionCards(id: string | null) {
  return useQuery({
    queryKey: keys.collectionCards(id ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/api/collections/{collection_id}/cards", {
          params: { path: { collection_id: id ?? "" } },
        }),
      ),
    enabled: Boolean(id),
  });
}

export function usePreviewCollection() {
  return useMutation({
    mutationFn: (content: string) =>
      unwrap(api.POST("/api/collections/preview", { body: { content } })),
  });
}

export function useCreateCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; content: string }) =>
      unwrap(api.POST("/api/collections", { body })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.collections });
      qc.invalidateQueries({ queryKey: keys.status });
    },
  });
}

export function useUpdateCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; content?: string }) =>
      unwrap(
        api.PATCH("/api/collections/{collection_id}", {
          params: { path: { collection_id: id } },
          body,
        }),
      ),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: keys.collections });
      qc.invalidateQueries({ queryKey: keys.collection(id) });
      qc.invalidateQueries({ queryKey: ["commanders", id] });
    },
  });
}

export function useDeleteCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/api/collections/{collection_id}", { params: { path: { collection_id: id } } }),
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.collections });
      qc.invalidateQueries({ queryKey: keys.status });
    },
  });
}

// --- commanders -------------------------------------------------------------------------

export function useCommanders(collection: string | null, colors?: string) {
  return useQuery({
    queryKey: keys.commanders(collection ?? "", colors),
    queryFn: () =>
      unwrap(
        api.GET("/api/commanders", {
          params: { query: { collection: collection ?? "", ...(colors ? { colors } : {}) } },
        }),
      ),
    enabled: Boolean(collection),
  });
}

export interface SuggestionParams {
  collection: string;
  theme?: string;
  colors?: string;
  top?: number;
  variety?: number;
  seed?: number;
}

export function useSuggestCommanders() {
  // This is an explicit action: each click must run again, even with identical
  // filters, so unseeded variety can return a fresh set of suggestions.
  return useMutation({
    mutationFn: (params: SuggestionParams) =>
      unwrap(api.GET("/api/commanders/suggestions", { params: { query: params } })),
  });
}

export function usePartners(collection: string | null, commander: string | null, enabled: boolean) {
  return useQuery({
    queryKey: keys.partners(collection ?? "", commander ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/api/commanders/partners", {
          params: { query: { collection: collection ?? "", commander: commander ?? "" } },
        }),
      ),
    enabled: Boolean(collection && commander && enabled),
  });
}

// --- builds & decks ---------------------------------------------------------------------------

export function useBuild() {
  return useMutation({
    mutationFn: (params: BuildParams) => unwrap(api.POST("/api/builds", { body: params })),
  });
}

export function useSaveBuild() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { build_id: string; name?: string | null }) =>
      unwrap(api.POST("/api/decks", { body })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.decks });
      qc.invalidateQueries({ queryKey: keys.status });
    },
  });
}

export interface DeckListParams {
  q?: string;
  commander?: string;
  source?: string;
  limit: number;
  offset: number;
}

export function useDecks(params: DeckListParams) {
  return useQuery({
    queryKey: keys.deckList(params),
    queryFn: () => unwrap(api.GET("/api/decks", { params: { query: params } })),
    placeholderData: keepPreviousData,
  });
}

export function useDeck(id: number | null) {
  return useQuery({
    queryKey: keys.deck(id ?? 0),
    queryFn: () =>
      unwrap(api.GET("/api/decks/{deck_id}", { params: { path: { deck_id: id ?? 0 } } })),
    enabled: id !== null && Number.isFinite(id),
  });
}

export function useUpdateDeck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; name?: string; notes?: string }) =>
      unwrap(api.PATCH("/api/decks/{deck_id}", { params: { path: { deck_id: id } }, body })),
    onSuccess: (deck) => {
      qc.setQueryData(keys.deck(deck.id), deck);
      qc.invalidateQueries({ queryKey: ["decks", "list"] });
    },
  });
}

export function useDeleteDeck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(api.DELETE("/api/decks/{deck_id}", { params: { path: { deck_id: id } } })),
    onSuccess: (_data, id) => {
      qc.removeQueries({ queryKey: keys.deck(id) });
      qc.invalidateQueries({ queryKey: ["decks", "list"] });
      qc.invalidateQueries({ queryKey: keys.status });
    },
  });
}

export function useImportDeck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { content: string; name?: string | null; filename?: string | null }) =>
      unwrap(api.POST("/api/decks/import", { body })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["decks", "list"] });
      qc.invalidateQueries({ queryKey: keys.status });
    },
  });
}

/** Download URL for a saved deck (the browser handles the file). */
export function exportUrl(
  id: number,
  format: "json" | "text" | "mtgo" | "moxfield" | "archidekt",
): string {
  return `/api/decks/${id}/export?format=${format}`;
}

/** Fetch a saved deck's export as text (for "copy to clipboard"). */
export async function fetchExport(
  id: number,
  format: "text" | "mtgo" | "moxfield" | "archidekt",
): Promise<string> {
  const response = await fetch(exportUrl(id, format));
  if (!response.ok) throw new Error(`Export failed (${response.status})`);
  return response.text();
}
