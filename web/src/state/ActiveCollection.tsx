// The collection every page works with, chosen in the header and remembered
// in localStorage. Falls back to the server's default when the stored one is gone.
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import { useCollections, useStatus } from "../api/queries";
import type { CollectionInfo } from "../api/types";

const STORAGE_KEY = "commanderai.collection";

interface ActiveCollectionValue {
  id: string | null;
  collection: CollectionInfo | null;
  collections: CollectionInfo[];
  setId: (id: string) => void;
  loading: boolean;
}

const Context = createContext<ActiveCollectionValue | null>(null);

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function ActiveCollectionProvider({ children }: { children: ReactNode }) {
  const { data: collections = [], isLoading } = useCollections();
  const { data: status } = useStatus();
  const [stored, setStored] = useState<string | null>(readStored);

  const id = useMemo(() => {
    if (collections.length === 0) return null;
    if (stored && collections.some((c) => c.id === stored)) return stored;
    const fallback = status?.default_collection;
    if (fallback && collections.some((c) => c.id === fallback)) return fallback;
    return collections[0]?.id ?? null;
  }, [collections, stored, status]);

  const setId = useCallback((next: string) => {
    setStored(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // storage unavailable: keep the choice for this session only
    }
  }, []);

  const value = useMemo<ActiveCollectionValue>(
    () => ({
      id,
      collection: collections.find((c) => c.id === id) ?? null,
      collections,
      setId,
      loading: isLoading,
    }),
    [id, collections, setId, isLoading],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useActiveCollection(): ActiveCollectionValue {
  const value = useContext(Context);
  if (!value) throw new Error("useActiveCollection must be used inside ActiveCollectionProvider");
  return value;
}
