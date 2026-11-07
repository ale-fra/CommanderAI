import {
  Badge,
  Button,
  Collapse,
  Group,
  NumberInput,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Skeleton,
  Slider,
  Stack,
  Table,
  Text,
  UnstyledButton,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconBulb, IconHammer } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useCommanders, useSuggestCommanders } from "../api/queries";
import type { CommanderEntry } from "../api/types";
import { useCardDetail } from "../components/CardDetail";
import { CardImage } from "../components/CardImage";
import { ColorPicker } from "../components/ColorPicker";
import { EmptyState, ErrorAlert, PageHeader } from "../components/Feedback";
import { ColorIdentity } from "../components/ManaCost";
import { ThemeSelect } from "../components/ThemeSelect";
import { toggleColor } from "../lib/colors";
import { plural } from "../lib/format";
import { patchParams, useUrlParams } from "../lib/useUrlParams";
import { useActiveCollection } from "../state/ActiveCollection";

function buildHref(name: string, collection: string | null, theme?: string | null) {
  const p = new URLSearchParams({ commander: name });
  if (collection) p.set("collection", collection);
  if (theme) p.set("theme", theme);
  return `/build?${p}`;
}

function CommanderTile({
  entry,
  collection,
}: {
  entry: CommanderEntry;
  collection: string | null;
}) {
  const openCard = useCardDetail();
  const { card } = entry;
  return (
    <Paper withBorder radius="md" p={8} h="100%">
      <Stack gap={6} h="100%">
        <UnstyledButton
          onClick={() => openCard(card.name, { collection })}
          aria-label={`${card.name} — show details`}
        >
          <CardImage name={card.name} images={card.images} radius="sm" />
        </UnstyledButton>
        <Text fw={600} size="sm" lineClamp={2} title={card.name}>
          {card.name}
        </Text>
        <Group gap={6} wrap="nowrap">
          <ColorIdentity colors={card.color_identity} size="sm" />
          <Text size="xs" c="dimmed">
            EDHREC {entry.edhrec_rank ? `#${entry.edhrec_rank}` : "—"}
          </Text>
        </Group>
        <Text size="xs" c="dimmed">
          {plural(entry.support, "supporting card")}
        </Text>
        {entry.partner_tags.length > 0 && (
          <Group gap={4}>
            {entry.partner_tags.map((t) => (
              <Badge key={t} size="xs" color="grape" variant="light">
                {t}
              </Badge>
            ))}
          </Group>
        )}
        <Button
          component={Link}
          to={buildHref(card.name, collection)}
          size="xs"
          variant="light"
          leftSection={<IconHammer size={14} />}
          mt="auto"
          aria-label={`Build with ${card.name}`}
        >
          Build
        </Button>
      </Stack>
    </Paper>
  );
}

function SuggestPanel({ collection }: { collection: string }) {
  const [theme, setTheme] = useState<string | null>(null);
  const [colors, setColors] = useState<string[]>([]);
  const [top, setTop] = useState<number>(5);
  const [variety, setVariety] = useState(0);
  const [seed, setSeed] = useState<number | "">("");
  const { data, error, isPending, mutate: suggest } = useSuggestCommanders();

  const run = () =>
    suggest({
      collection,
      ...(theme ? { theme } : {}),
      ...(colors.length ? { colors: colors.filter((c) => c !== "C").join("") || "colorless" } : {}),
      top,
      ...(variety > 0 ? { variety } : {}),
      ...(seed !== "" ? { seed: Number(seed) } : {}),
    });

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          Rank the commanders you own by how many of your cards support them — optionally for a
          theme or colors.
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
          <ThemeSelect label="Theme" placeholder="Any theme" value={theme} onChange={setTheme} />
          <Stack gap={4}>
            <Text size="sm" fw={500}>
              Colors
            </Text>
            <ColorPicker
              value={colors}
              onChange={setColors}
              withColorless={false}
              label="Suggestion colors"
            />
          </Stack>
          <NumberInput
            label="How many"
            min={1}
            max={50}
            value={top}
            onChange={(v) => setTop(Number(v) || 5)}
          />
          <Stack gap={4}>
            <Text size="sm" fw={500}>
              Variety {variety.toFixed(1)}
            </Text>
            <Slider
              min={0}
              max={1}
              step={0.1}
              value={variety}
              onChange={setVariety}
              aria-label="Variety"
              thumbLabel="Variety"
              label={null}
            />
            <NumberInput
              aria-label="Seed"
              placeholder="Seed (optional)"
              size="xs"
              value={seed}
              onChange={(v) => setSeed(v === "" ? "" : Number(v))}
              allowDecimal={false}
            />
          </Stack>
        </SimpleGrid>
        <Group>
          <Button onClick={run} loading={isPending} leftSection={<IconBulb size={16} />}>
            Suggest
          </Button>
          {data?.seed != null && (
            <Text size="xs" c="dimmed">
              Seed {data.seed} (variety {data.variety.toFixed(2)}) — enter it to repeat these picks.
            </Text>
          )}
        </Group>
        {error && <ErrorAlert error={error} />}
        {data && data.suggestions.length === 0 && (
          <Text c="dimmed">No commander fits these criteria.</Text>
        )}
        {data && data.suggestions.length > 0 && (
          <Table verticalSpacing={6} aria-label="Suggested commanders">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={30}>#</Table.Th>
                <Table.Th>Commander</Table.Th>
                <Table.Th ta="right">Supporting cards</Table.Th>
                <Table.Th ta="right" visibleFrom="sm">
                  Theme fit
                </Table.Th>
                <Table.Th ta="right" visibleFrom="sm">
                  EDHREC
                </Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.suggestions.map((s, i) => (
                <Table.Tr key={s.commander.card.name}>
                  <Table.Td>{i + 1}</Table.Td>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      <ColorIdentity colors={s.commander.card.color_identity} size="sm" />
                      <Text size="sm" fw={500}>
                        {s.commander.card.name}
                      </Text>
                    </Group>
                  </Table.Td>
                  <Table.Td ta="right">{s.support}</Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">
                    {s.theme_fit}
                  </Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">
                    {s.edhrec_rank < 99999 ? `#${s.edhrec_rank}` : "—"}
                  </Table.Td>
                  <Table.Td ta="right">
                    <Button
                      component={Link}
                      to={buildHref(s.commander.card.name, collection, data.theme)}
                      size="compact-xs"
                      variant="light"
                      aria-label={`Build with ${s.commander.card.name}`}
                    >
                      Build
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Stack>
    </Paper>
  );
}

export default function CommandersPage() {
  const { id, collection } = useActiveCollection();
  const [params, updateParams] = useUrlParams();
  const colors = (params.get("c") ?? "").split("").filter(Boolean);
  const sort =
    (["rank", "support", "name"] as const).find((s) => s === params.get("sort")) ?? "rank";
  const [suggestOpen, { toggle }] = useDisclosure(params.get("suggest") === "1");
  const query = colors.length ? colors.filter((c) => c !== "C").join("") || "colorless" : undefined;
  const { data, error, isLoading, refetch } = useCommanders(id, query);

  const update = (key: string, value: string | null) =>
    updateParams((latest) => patchParams(latest, { [key]: value }));

  const sorted = useMemo(() => {
    const list = [...(data ?? [])];
    if (sort === "support")
      list.sort((a, b) => b.support - a.support || a.card.name.localeCompare(b.card.name));
    if (sort === "name") list.sort((a, b) => a.card.name.localeCompare(b.card.name));
    return list;
  }, [data, sort]);

  return (
    <Stack gap="md">
      <PageHeader
        title="Commanders"
        subtitle={`Legal commanders in ${collection?.name ?? "your collection"}`}
        actions={
          <Button
            variant={suggestOpen ? "filled" : "light"}
            leftSection={<IconBulb size={16} />}
            onClick={toggle}
          >
            Suggest a commander
          </Button>
        }
      />
      <Collapse expanded={suggestOpen}>{id && <SuggestPanel key={id} collection={id} />}</Collapse>

      <Paper withBorder p="sm" radius="md">
        <Group justify="space-between" gap="sm">
          <Group gap="sm">
            <Text size="sm" fw={500}>
              Colors within
            </Text>
            <ColorPicker
              value={colors}
              onToggle={(c) =>
                updateParams((latest) =>
                  patchParams(latest, {
                    c:
                      toggleColor((latest.get("c") ?? "").split("").filter(Boolean), c).join("") ||
                      null,
                  }),
                )
              }
              label="Commander colors"
            />
          </Group>
          <SegmentedControl
            size="xs"
            value={sort}
            onChange={(v) => update("sort", v === "rank" ? null : v)}
            aria-label="Sort commanders"
            data={[
              { value: "rank", label: "Popularity" },
              { value: "support", label: "Support" },
              { value: "name", label: "Name" },
            ]}
          />
        </Group>
      </Paper>

      {error && <ErrorAlert error={error} onRetry={() => refetch()} />}
      {isLoading && (
        <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
          {Array.from({ length: 5 }, (_, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders
            <Skeleton key={i} h={300} radius="md" />
          ))}
        </SimpleGrid>
      )}
      {data && (
        <Text size="sm" c="dimmed" aria-live="polite">
          {plural(sorted.length, "commander")}
        </Text>
      )}
      {data && sorted.length === 0 && (
        <EmptyState title="No commanders">
          No legendary creature (or card that can be your commander) matches these colors in this
          collection.
        </EmptyState>
      )}
      <SimpleGrid cols={{ base: 2, xs: 3, md: 4, lg: 5, xl: 6 }} spacing="sm">
        {sorted.map((entry) => (
          <CommanderTile key={entry.card.name} entry={entry} collection={id} />
        ))}
      </SimpleGrid>
    </Stack>
  );
}
