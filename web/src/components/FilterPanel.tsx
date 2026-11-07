import {
  Button,
  Chip,
  Group,
  MultiSelect,
  NumberInput,
  RangeSlider,
  SegmentedControl,
  Stack,
  Switch,
  Text,
} from "@mantine/core";
import {
  activeFilterCount,
  CARD_TYPES,
  type CardFilters,
  CMC_MAX,
  type ColorMode,
  DEFAULT_FILTERS,
  RARITIES,
  ROLES,
} from "../lib/filters";
import { titleCase } from "../lib/format";
import { ColorPicker } from "./ColorPicker";

interface FilterPanelProps {
  value: CardFilters;
  /** Receives only the changed fields, so the page can merge with the latest state. */
  onChange: (patch: Partial<CardFilters>) => void;
  /** Toggle one color on top of the latest state. */
  onToggleColor: (color: string) => void;
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Stack gap={6}>
      <Text size="xs" fw={700} c="dimmed" tt="uppercase">
        {label}
      </Text>
      {children}
    </Stack>
  );
}

export function FilterPanel({ value: f, onChange, onToggleColor }: FilterPanelProps) {
  const set = <K extends keyof CardFilters>(key: K, v: CardFilters[K]) =>
    onChange({ [key]: v } as Partial<CardFilters>);
  return (
    <Stack gap="lg">
      <Section label="Color identity">
        <ColorPicker value={f.colors} onToggle={onToggleColor} label="Color identity" />
        <SegmentedControl
          size="xs"
          value={f.colorMode}
          onChange={(v) => set("colorMode", v as ColorMode)}
          aria-label="Color matching"
          data={[
            { value: "within", label: "Within" },
            { value: "exactly", label: "Exactly" },
            { value: "including", label: "Including" },
          ]}
          disabled={f.colors.length === 0}
        />
        <Text size="xs" c="dimmed">
          {f.colorMode === "within" && "Cards playable in a deck of these colors."}
          {f.colorMode === "exactly" && "Cards with exactly these colors."}
          {f.colorMode === "including" && "Cards that include all of these colors."}
        </Text>
      </Section>

      <Section label="Card type">
        <MultiSelect
          aria-label="Card types"
          placeholder="Any type"
          data={[...CARD_TYPES]}
          value={f.types}
          onChange={(v) => set("types", v)}
          clearable
        />
      </Section>

      <Section label="Mana value">
        <RangeSlider
          aria-label="Mana value range"
          thumbFromLabel="Minimum mana value"
          thumbToLabel="Maximum mana value"
          min={0}
          max={CMC_MAX}
          minRange={0}
          value={f.cmc ?? [0, CMC_MAX]}
          onChange={(v) => set("cmc", v[0] === 0 && v[1] === CMC_MAX ? null : v)}
          marks={[0, 2, 4, 6, 8, 10].map((v) => ({
            value: v,
            label: v === CMC_MAX ? "10+" : String(v),
          }))}
          label={(v) => (v === CMC_MAX ? "10+" : String(v))}
          mb="md"
        />
      </Section>

      <Section label="Role">
        <Chip.Group multiple value={f.roles} onChange={(v) => set("roles", v)}>
          <Group gap={6}>
            {ROLES.map((r) => (
              <Chip key={r} value={r} size="xs">
                {titleCase(r)}
              </Chip>
            ))}
          </Group>
        </Chip.Group>
      </Section>

      <Section label="Rarity">
        <Chip.Group multiple value={f.rarities} onChange={(v) => set("rarities", v)}>
          <Group gap={6}>
            {RARITIES.map((r) => (
              <Chip key={r} value={r} size="xs">
                {titleCase(r)}
              </Chip>
            ))}
          </Group>
        </Chip.Group>
      </Section>

      <Section label="Price">
        <NumberInput
          aria-label="Maximum price in USD"
          placeholder="Any price"
          prefix="≤ $"
          min={0}
          decimalScale={2}
          value={f.maxPrice ?? ""}
          onChange={(v) => set("maxPrice", v === "" ? null : Number(v))}
        />
      </Section>

      <Switch
        label="Commanders only"
        checked={f.commandersOnly}
        onChange={(e) => set("commandersOnly", e.currentTarget.checked)}
      />

      <Button
        variant="subtle"
        onClick={() => {
          const { q: _q, sort: _s, dir: _d, ...reset } = DEFAULT_FILTERS;
          onChange(reset);
        }}
        disabled={activeFilterCount(f) === 0}
      >
        Reset filters
      </Button>
    </Stack>
  );
}
