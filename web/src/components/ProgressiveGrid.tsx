import { SimpleGrid, type SimpleGridProps } from "@mantine/core";
import { useIntersection } from "@mantine/hooks";
import { type ReactNode, useEffect, useState } from "react";

/** Show `chunk` items, then more each time the sentinel scrolls into view. */
export function useProgressive<T>(items: T[], chunk = 60) {
  const [count, setCount] = useState(chunk);
  const { ref, entry } = useIntersection({ rootMargin: "800px" });

  // biome-ignore lint/correctness/useExhaustiveDependencies: start over when the list changes
  useEffect(() => setCount(chunk), [items, chunk]);

  useEffect(() => {
    if (entry?.isIntersecting && count < items.length) setCount((c) => c + chunk);
  }, [entry?.isIntersecting, count, items.length, chunk]);

  const sentinel =
    count < items.length ? (
      <div ref={ref} style={{ height: 1 }} aria-hidden="true" data-testid="load-more" />
    ) : null;
  return { visible: items.slice(0, count), sentinel };
}

interface ProgressiveGridProps<T> extends Omit<SimpleGridProps, "children"> {
  items: T[];
  render: (item: T, index: number) => ReactNode;
  getKey: (item: T) => string;
  chunk?: number;
}

export function ProgressiveGrid<T>({
  items,
  render,
  getKey,
  chunk = 60,
  ...grid
}: ProgressiveGridProps<T>) {
  const { visible, sentinel } = useProgressive(items, chunk);
  return (
    <>
      <SimpleGrid {...grid}>
        {visible.map((item, i) => (
          <div key={getKey(item)}>{render(item, i)}</div>
        ))}
      </SimpleGrid>
      {sentinel}
    </>
  );
}
