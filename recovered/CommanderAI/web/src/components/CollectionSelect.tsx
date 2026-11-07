import { Select } from "@mantine/core";
import { useMemo } from "react";
import { useLocation, useNavigate } from "react-router";
import { formFromSearch, formToSearch } from "../lib/buildForm";
import { useActiveCollection } from "../state/ActiveCollection";

const GROUPS: Record<string, string> = {
  default: "Mine",
  stored: "Uploaded",
  builtin: "Samples & precons",
};

/** Header selector for the active collection. */
export function CollectionSelect({ w = 240 }: { w?: number | string }) {
  const { id, collections, setId } = useActiveCollection();
  const location = useLocation();
  const navigate = useNavigate();
  const select = (next: string | null) => {
    if (!next || next === id) return;
    setId(next);
    if (location.pathname === "/build") {
      const form = formFromSearch(new URLSearchParams(location.search), id ?? "");
      const search = formToSearch({
        ...form,
        collection: next,
        commander: null,
        partner: null,
      });
      navigate({ pathname: "/build", search: search.toString() }, { replace: true });
    }
  };
  const data = useMemo(() => {
    const order = ["default", "stored", "builtin"] as const;
    return order
      .map((kind) => ({
        group: GROUPS[kind] ?? kind,
        items: collections
          .filter((c) => c.kind === kind)
          .map((c) => ({ value: c.id, label: `${c.name} (${c.copies})` })),
      }))
      .filter((g) => g.items.length > 0);
  }, [collections]);
  return (
    <Select
      aria-label="Active collection"
      data={data}
      value={id}
      onChange={select}
      allowDeselect={false}
      w={w}
      comboboxProps={{ withinPortal: true }}
      size="sm"
    />
  );
}
