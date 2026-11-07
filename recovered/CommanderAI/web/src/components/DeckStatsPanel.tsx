import { BarChart } from "@mantine/charts";
import { Group, Paper, Progress, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import type { DeckStats } from "../api/types";
import { COLOR_NAMES, COLOR_SWATCH, WUBRG } from "../lib/colors";
import { formatPrice } from "../lib/format";
import { ROLE_ORDER, roleLabel } from "./RoleBadge";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Paper withBorder p="sm" radius="md">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700} fz="lg">
        {value}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Paper>
  );
}

export function StatSummary({ stats }: { stats: DeckStats }) {
  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
      <Stat label="Cards" value={String(stats.card_count)} hint={`${stats.lands} lands`} />
      <Stat
        label="Estimated price"
        value={formatPrice(stats.total_price)}
        hint={
          stats.unpriced_cards
            ? `${stats.unpriced_cards} cards without price data`
            : "all cards priced"
        }
      />
      <Stat label="Average mana value" value={stats.avg_cmc.toFixed(2)} hint="nonland cards" />
      <Stat
        label="Colors"
        value={WUBRG.filter((c) => (stats.color_pips[c] ?? 0) > 0).join("") || "C"}
        hint="from mana costs"
      />
    </SimpleGrid>
  );
}

export function DeckStatsPanel({ stats }: { stats: DeckStats }) {
  const curve = Object.entries(stats.mana_curve).map(([mv, count]) => ({ mv, count }));
  const pips = WUBRG.map((c) => ({
    color: COLOR_NAMES[c] ?? c,
    symbols: stats.color_pips[c] ?? 0,
    key: c,
  })).filter((p) => p.symbols > 0);
  const roles = ROLE_ORDER.map((r) => ({
    role: roleLabel(r),
    cards: stats.roles[r] ?? 0,
    target: stats.role_targets[r] ?? 0,
  }));
  const typeTotal = Object.values(stats.types).reduce((a, b) => a + b, 0) || 1;
  const pipTotal = pips.reduce((a, p) => a + p.symbols, 0) || 1;
  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Paper withBorder p="md" radius="md">
          <Title order={4} fz="sm" mb="sm">
            Mana curve (nonland cards)
          </Title>
          <Text className="sr-only">
            {curve.map((c) => `Mana value ${c.mv}: ${c.count} cards`).join(". ")}
          </Text>
          <BarChart
            aria-hidden="true"
            h={200}
            data={curve}
            dataKey="mv"
            series={[{ name: "count", label: "Cards", color: "brand.5" }]}
            withTooltip
            tickLine="none"
          />
        </Paper>
        <Paper withBorder p="md" radius="md">
          <Title order={4} fz="sm" mb="sm">
            Roles vs targets
          </Title>
          <Text className="sr-only">
            {roles.map((r) => `${r.role}: ${r.cards} cards, target ${r.target}`).join(". ")}
          </Text>
          <BarChart
            aria-hidden="true"
            h={200}
            data={roles}
            dataKey="role"
            series={[
              { name: "cards", label: "In deck", color: "brand.5" },
              { name: "target", label: "Target", color: "gray.5" },
            ]}
            withLegend
            tickLine="none"
            xAxisProps={{ interval: 0, fontSize: 11 }}
          />
        </Paper>
        <Paper withBorder p="md" radius="md">
          <Title order={4} fz="sm" mb="sm">
            Colored mana symbols
          </Title>
          {pips.length === 0 ? (
            <Text size="sm" c="dimmed">
              Colorless deck.
            </Text>
          ) : (
            <Stack gap={8}>
              {pips.map((p) => (
                <div key={p.key}>
                  <Group justify="space-between">
                    <Group gap={6}>
                      <i className={`ms ms-cost ms-${p.key.toLowerCase()}`} aria-hidden="true" />
                      <Text size="sm">{p.color}</Text>
                    </Group>
                    <Text size="sm" c="dimmed">
                      {p.symbols}
                    </Text>
                  </Group>
                  <Progress
                    value={(p.symbols / pipTotal) * 100}
                    color={COLOR_SWATCH[p.key]}
                    size="sm"
                    aria-label={`${p.color}: ${p.symbols} symbols`}
                  />
                </div>
              ))}
            </Stack>
          )}
        </Paper>
        <Paper withBorder p="md" radius="md">
          <Title order={4} fz="sm" mb="sm">
            Card types
          </Title>
          <Stack gap={8}>
            {Object.entries(stats.types).map(([type, count]) => (
              <div key={type}>
                <Group justify="space-between">
                  <Text size="sm">{type}</Text>
                  <Text size="sm" c="dimmed">
                    {count}
                  </Text>
                </Group>
                <Progress
                  value={(count / typeTotal) * 100}
                  size="sm"
                  aria-label={`${type}: ${count} cards`}
                />
              </div>
            ))}
          </Stack>
        </Paper>
      </SimpleGrid>
    </Stack>
  );
}
