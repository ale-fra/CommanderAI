import { useCallback } from "react";
import { useSearchParams } from "react-router";

/**
 * URL search params with updates that always build on the *latest* URL.
 *
 * React Router's functional `setSearchParams(prev => …)` passes the params of the
 * last render, so two quick changes (e.g. two color toggles) would lose the first.
 * `window.location.search` is updated synchronously on every navigation.
 */
export function useUrlParams() {
  const [params, setParams] = useSearchParams();
  const update = useCallback(
    (fn: (latest: URLSearchParams) => URLSearchParams) =>
      setParams(fn(new URLSearchParams(window.location.search)), { replace: true }),
    [setParams],
  );
  return [params, update] as const;
}

/** Set/delete keys on top of the latest URL (null or "" deletes). */
export function patchParams(
  latest: URLSearchParams,
  changes: Record<string, string | null>,
): URLSearchParams {
  const next = new URLSearchParams(latest);
  for (const [key, value] of Object.entries(changes)) {
    if (value) next.set(key, value);
    else next.delete(key);
  }
  return next;
}
