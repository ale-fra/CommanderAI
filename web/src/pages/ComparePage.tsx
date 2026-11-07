import {
  Badge,
  Button,
  Grid,
  Group,
  Loader,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconArrowsLeftRight } from "@tabler/icons-react";
import { useMemo } from "react";
import { Link } from "react-router";
import { useDeck, useDecks } from "../api/queries";
import type { DeckDetail } from "../api/types";
import { ErrorAlert, PageHeader } from "../components/Feedback";
import { RoleBadge } from "../components/RoleBadge";
import { type CompareRow, compareDecks } from "../lib/compare";
import { formatPrice } from "../lib/format";
import { patchParams, useUrlParams } from "../lib/useUrlParams";

function RowsTable({
  rows,
  label,
  counts,
}: {
  rows: CompareRow[];
  label: string;
  counts: "a" | "b" | "both";
}) {
  if (rows.length === 0)
    return (
      <Text size="sm" c="dimmed">
        None.
      </Text>
    );
  return (
    <Table verticalSpacing={4} aria-label={label}>
      <Table.Tbody>
        {rows.map((r) => (
          <Table.Tr key={r.name}>
            <Table.Td>
              <Text size="sm">{r.name}</Text>
            </Table.Td>
            <Table.Td w={110}>
              <RoleBadge role={r.slot} size="xs" />
            </Table.Td>
            <Table.Td w={70} ta="right">
              <Text size="xs" c="dimmed">
                {counts === "a"
                  ? `×${r.a}`
                  : counts === "b"
                    ? `×${r.b}`
                    : r.a === r.b
                      ? `×${r.a}`
                      : `${r.a} → ${r.b}`}
              </Text>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

function DeckHeader({ deck, label }: { deck: DeckDetail; label: string }) {
  return (
    <Paper withBorder p="sm" radius="md">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={600} component={Link} to={`/decks/${deck.id}`}>
        {deck.name}
      </Text>
      <Text size="xs" c="dimmed">
        {formatPrice(deck.stats.total_price)} · avg mana value {deck.stats.avg_cmc.toFixed(2)} ·{" "}
        {deck.stats.lands} lands
      </Text>
    </Paper>
  );
}

export default function ComparePage() {
  const [params, updateParams] = useUrlParams();
  const a = Number(params.get("a")) || null;
  const b = Number(params.get("b")) || null;
  const deckA = useDeck(a);
  const deckB = useDeck(b);
  const { data: list } = useDecks({ limit: 500, offset: 0 });
  const options = (list?.items ?? []).map((d) => ({
    value: String(d.id),
    label: `#${d.id} ${d.name}`,
  }));
  const diff = useMemo(
    () => (deckA.data && deckB.data ? compareDecks(deckA.data.deck, deckB.data.deck) : null),
    [deckA.data, deckB.data],
  );
  const set = (key: "a" | "b", value: string | null) =>
    updateParams((latest) => patchParams(latest, { [key]: value }));

  return (
    <Stack gap="md">
      <PageHeader title="Compare decks" subtitle="Cards only in one deck, and cards they share." />
      <Group align="flex-end" gap="sm">
        <Select
          label="Deck A"
          data={options}
          value={a ? String(a) : null}
          onChange={(v) => set("a", v)}
          searchable
          w={280}
        />
        <Button
          variant="default"
          aria-label="Swap decks"
          onClick={() =>
            updateParams((latest) =>
              patchParams(latest, { a: latest.get("b"), b: latest.get("a") }),
            )
          }
        >
          <IconArrowsLeftRight size={16} />
        </Button>
        <Select
          label="Deck B"
          data={options}
          value={b ? String(b) : null}
          onChange={(v) => set("b", v)}
          searchable
          w={280}
        />
      </Group>
      {(deckA.error || deckB.error) && <ErrorAlert error={deckA.error ?? deckB.error} />}
      {(deckA.isLoading || deckB.isLoading) && <Loader />}
      {deckA.data && deckB.data && diff && (
        <>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <DeckHeader deck={deckA.data} label="Deck A" />
            <DeckHeader deck={deckB.data} label="Deck B" />
          </SimpleGrid>
          {diff.commandersA.join() !== diff.commandersB.join() && (
            <Text size="sm">
              Commanders: <b>{diff.commandersA.join(" + ")}</b> vs{" "}
              <b>{diff.commandersB.join(" + ")}</b>
            </Text>
          )}
          <Grid gap="md">
            <Grid.Col span={{ base: 12, md: 4 }}>
              <Title order={3} fz="md" mb="xs">
                Only in A{" "}
                <Badge color="red" variant="light">
                  {diff.onlyA.length}
                </Badge>
              </Title>
              <RowsTable rows={diff.onlyA} label="Cards only in deck A" counts="a" />
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 4 }}>
              <Title order={3} fz="md" mb="xs">
                Only in B{" "}
                <Badge color="teal" variant="light">
                  {diff.onlyB.length}
                </Badge>
              </Title>
              <RowsTable rows={diff.onlyB} label="Cards only in deck B" counts="b" />
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 4 }}>
              <Title order={3} fz="md" mb="xs">
                Shared <Badge variant="light">{diff.shared.length}</Badge>
              </Title>
              <RowsTable rows={diff.shared} label="Cards in both decks" counts="both" />
            </Grid.Col>
          </Grid>
        </>
      )}
      {(!a || !b) && (
        <Text c="dimmed" size="sm">
          Choose two decks above, or select two decks in the library and press Compare.
        </Text>
      )}
    </Stack>
  );
}
