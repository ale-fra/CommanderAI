import { Select, type SelectProps } from "@mantine/core";
import { useMemo } from "react";
import { useVocabulary } from "../api/queries";
import { titleCase } from "../lib/format";

const label = (name: string) => titleCase(name.replace(/_/g, " "));

/** Theme picker: archetypes, creature tribes and aliases (which resolve to an archetype/tribe). */
export function ThemeSelect(props: Omit<SelectProps, "data">) {
  const { data: vocab } = useVocabulary();
  const data = useMemo(() => {
    if (!vocab) return [];
    // Aliases that merely repeat an archetype/tribe name ("lifedrain" → lifedrain) are dropped:
    // option values must be unique.
    const canonical = new Set([...vocab.archetypes, ...vocab.tribes].map((t) => t.name));
    return [
      {
        group: "Archetypes",
        items: vocab.archetypes.map((a) => ({ value: a.name, label: label(a.name) })),
      },
      {
        group: "Tribes",
        items: vocab.tribes.map((t) => ({ value: t.name, label: label(t.name) })),
      },
      {
        group: "Aliases",
        items: vocab.aliases
          .filter((a) => !canonical.has(a.alias))
          .map((a) => ({ value: a.alias, label: `${a.alias} → ${label(a.target)}` })),
      },
    ];
  }, [vocab]);
  return <Select searchable clearable data={data} nothingFoundMessage="No such theme" {...props} />;
}
