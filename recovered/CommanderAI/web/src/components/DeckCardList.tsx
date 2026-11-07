import {
  Group,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { useLocalStorage } from "@mantine/hooks";
import { IconLayoutGrid, IconList } from "@tabler/icons-react";
import { useMemo } from "react";
import type { CardSummary, DeckSlot, DeckView } from "../api/types";
import { formatPrice } from "../lib/format";
import { useCardDetail } from "./CardDetail";
import { CardTile } from "./CardTile";
import { ManaCost } from "./ManaCost";
import { ROLE_COLORS, ROLE_ORDER, roleLabel } from "./RoleBadge";

interface Entry {
  card: CardSummary;
  count: number;
  reason: string;
}

/** Cards grouped by role; duplicate picks (basic lands) collapse into one entry with a count. */
export function groupDeck(deck: DeckView): { slot: DeckSlot; entries: Entry[]; total: number }[] {
  const groups = new Map<DeckSlot, Map<string, Entry>>();
  for (const pick of deck.cards) {
    const group = groups.get(pick.slot) ?? new Map<string, Entry>();
    const cur = group.get(pick.card.name);
    if (cur) cur.count += 1;
    else group.set(pick.card.name, { card: pick.card, count: 1, reason: pick.reason });
    groups.set(pick.slot, group);
  }
  return ROLE_ORDER.filter((slot) => groups.has(slot)).map((slot) => {
    const entries = [...(groups.get(slot)?.values() ?? [])].sort(
      (a, b) => a.card.cmc - b.card.cmc || a.card.name.localeCompare(b.card.name),
    );
    return { slot, entries, total: entries.reduce((n, e) => n + e.count, 0) };
  });
}

export function DeckCardList({
  deck,
  showReasons = true,
}: {
  deck: DeckView;
  showReasons?: boolean;
}) {
  const [view, setView] = useLocalStorage<"grid" | "list">({
    key: "commanderai.deck-view",
    defaultValue: "list",
  });
  const openCard = useCardDetail();
  const groups = useMemo(() => groupDeck(deck), [deck]);
  const commanders = [deck.commander, ...(deck.partner ? [deck.partner] : [])];

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          {commanders.map((c) => c.name).join(" + ")} + {deck.cards.length} cards
        </Text>
        <SegmentedControl
          size="xs"
          value={view}
          onChange={(v) => setView(v as "grid" | "list")}
          aria-label="Card layout"
          data={[
            { value: "list", label: <IconList size={16} aria-label="List" /> },
            { value: "grid", label: <IconLayoutGrid size={16} aria-label="Grid" /> },
          ]}
        />
      </Group>
      {groups.map(({ slot, entries, total }) => (
        <section key={slot} aria-label={`${roleLabel(slot)} (${total})`}>
          <Title
            order={4}
            fz="sm"
            mb={6}
            style={{ color: `var(--mantine-color-${ROLE_COLORS[slot]}-light-color)` }}
            tt="uppercase"
            lts={0.5}
          >
            {roleLabel(slot)} ({total})
          </Title>
          {view === "grid" ? (
            <SimpleGrid cols={{ base: 2, xs: 3, sm: 4, lg: 6 }} spacing="sm">
              {entries.map((e) => (
                <CardTile
                  key={e.card.name}
                  card={e.card}
                  quantity={e.count}
                  onOpen={(n) => openCard(n)}
                />
              ))}
            </SimpleGrid>
          ) : (
            <Table highlightOnHover verticalSpacing={4} layout="fixed">
              <Table.Tbody>
                {entries.map((e) => (
                  <Table.Tr key={e.card.name}>
                    <Table.Td w={44} c="dimmed">
                      {e.count}×
                    </Table.Td>
                    <Table.Td>
                      <UnstyledButton
                        onClick={() => openCard(e.card.name)}
                        style={{ maxWidth: "100%" }}
                      >
                        <Text size="sm" fw={500} truncate>
                          {e.card.name}
                        </Text>
                      </UnstyledButton>
                      {showReasons && e.reason && (
                        <Text size="xs" c="dimmed" truncate>
                          {e.reason}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td w={{ base: 90, sm: 130 }} ta="right">
                      <ManaCost cost={e.card.mana_cost} size="sm" />
                    </Table.Td>
                    <Table.Td w={70} ta="right" visibleFrom="xs">
                      <Text size="xs" c="dimmed">
                        {formatPrice(e.card.price_usd)}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </section>
      ))}
    </Stack>
  );
}
