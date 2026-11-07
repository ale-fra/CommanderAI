import {
  ActionIcon,
  Avatar,
  Badge,
  Button,
  Checkbox,
  Group,
  Menu,
  Pagination,
  Paper,
  SegmentedControl,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  UnstyledButton,
} from "@mantine/core";
import { useDebouncedCallback } from "@mantine/hooks";
import {
  IconArrowsDiff,
  IconDots,
  IconDownload,
  IconFileImport,
  IconHammer,
  IconSearch,
} from "@tabler/icons-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { exportUrl, useDecks } from "../api/queries";
import type { DeckSummary } from "../api/types";
import { EmptyState, ErrorAlert, PageHeader } from "../components/Feedback";
import { ColorIdentity } from "../components/ManaCost";
import { formatDate, formatPrice, plural } from "../lib/format";
import { patchParams, useUrlParams } from "../lib/useUrlParams";
import { DeleteDeckModal, ImportDeckModal, RenameDeckModal } from "./DeckModals";

const PAGE_SIZE = 20;

export const SOURCE_LABELS: Record<string, string> = {
  api: "Web UI",
  cli: "CLI",
  import: "Imported",
  legacy: "Legacy file",
};

const SOURCE_COLORS: Record<string, string> = {
  api: "brand",
  cli: "blue",
  import: "teal",
  legacy: "gray",
};

export function SourceBadge({ source }: { source: string }) {
  return (
    <Badge variant="light" color={SOURCE_COLORS[source] ?? "gray"} size="sm">
      {SOURCE_LABELS[source] ?? source}
    </Badge>
  );
}

function colorsOf(deck: DeckSummary): string[] {
  return deck.colors === "C" ? [] : deck.colors.split("");
}

export default function DecksPage() {
  const [params, updateParams] = useUrlParams();
  const q = params.get("q") ?? "";
  const source = params.get("source") ?? "all";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [search, setSearch] = useState(q);
  const [selected, setSelected] = useState<number[]>([]);
  const [importing, setImporting] = useState(false);
  const [renaming, setRenaming] = useState<DeckSummary | null>(null);
  const [deleting, setDeleting] = useState<DeckSummary | null>(null);
  const navigate = useNavigate();

  const { data, error, isLoading, refetch } = useDecks({
    ...(q ? { q } : {}),
    ...(source !== "all" ? { source } : {}),
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  const update = (changes: Record<string, string | null>) =>
    updateParams((latest) => patchParams(latest, changes));
  const pushSearch = useDebouncedCallback(
    (value: string) => update({ q: value.trim() || null, page: null }),
    250,
  );
  const toggle = (id: number) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <Stack gap="md">
      <PageHeader
        title="Decks"
        subtitle={data ? `${plural(data.total, "saved deck")}` : "Your saved decks"}
        actions={
          <>
            <Button
              variant="default"
              leftSection={<IconFileImport size={16} />}
              onClick={() => setImporting(true)}
            >
              Import
            </Button>
            <Button component={Link} to="/build" leftSection={<IconHammer size={16} />}>
              New deck
            </Button>
          </>
        }
      />

      <Paper withBorder p="sm" radius="md">
        <Group gap="sm" justify="space-between">
          <TextInput
            aria-label="Search decks"
            placeholder="Search deck or commander name"
            leftSection={<IconSearch size={16} />}
            value={search}
            onChange={(e) => {
              setSearch(e.currentTarget.value);
              pushSearch(e.currentTarget.value);
            }}
            style={{ flex: "1 1 240px" }}
          />
          <SegmentedControl
            value={source}
            onChange={(v) => update({ source: v === "all" ? null : v, page: null })}
            aria-label="Deck source"
            data={[
              { value: "all", label: "All" },
              { value: "api", label: "Web UI" },
              { value: "cli", label: "CLI" },
              { value: "import", label: "Imported" },
              { value: "legacy", label: "Legacy" },
            ]}
            size="xs"
          />
        </Group>
      </Paper>

      {selected.length > 0 && (
        <Paper withBorder p="xs" radius="md">
          <Group justify="space-between">
            <Text size="sm">
              {selected.length === 1 ? "Select one more deck to compare." : "Two decks selected."}
            </Text>
            <Group gap="xs">
              <Button size="xs" variant="subtle" onClick={() => setSelected([])}>
                Clear
              </Button>
              <Button
                size="xs"
                leftSection={<IconArrowsDiff size={14} />}
                disabled={selected.length !== 2}
                onClick={() => navigate(`/decks/compare?a=${selected[0]}&b=${selected[1]}`)}
              >
                Compare
              </Button>
            </Group>
          </Group>
        </Paper>
      )}

      {error && <ErrorAlert error={error} onRetry={() => refetch()} />}
      {isLoading && <Skeleton h={200} radius="md" />}
      {data && data.total === 0 && (
        <EmptyState
          title={q || source !== "all" ? "No decks match" : "No saved decks yet"}
          action={
            <Button component={Link} to="/build" leftSection={<IconHammer size={16} />}>
              Build a deck
            </Button>
          }
        >
          {q || source !== "all"
            ? "Try another search or source."
            : "Build a deck and press Save, or import one."}
        </EmptyState>
      )}
      {data && data.items.length > 0 && (
        <Table highlightOnHover verticalSpacing="sm" aria-label="Saved decks">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={36}>
                <span className="sr-only">Select to compare</span>
              </Table.Th>
              <Table.Th>Deck</Table.Th>
              <Table.Th visibleFrom="sm">Colors</Table.Th>
              <Table.Th ta="right" visibleFrom="md">
                Cards
              </Table.Th>
              <Table.Th ta="right" visibleFrom="xs">
                Price
              </Table.Th>
              <Table.Th visibleFrom="md">Source</Table.Th>
              <Table.Th visibleFrom="lg">Created (UTC)</Table.Th>
              <Table.Th w={44}>
                <span className="sr-only">Actions</span>
              </Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.items.map((d) => {
              const commanders = d.partner ? `${d.commander} + ${d.partner}` : d.commander;
              return (
                <Table.Tr key={d.id}>
                  <Table.Td>
                    <Checkbox
                      aria-label={`Select ${d.name} to compare`}
                      checked={selected.includes(d.id)}
                      onChange={() => toggle(d.id)}
                    />
                  </Table.Td>
                  <Table.Td>
                    <UnstyledButton
                      component={Link}
                      to={`/decks/${d.id}`}
                      style={{ display: "block" }}
                    >
                      <Group gap="sm" wrap="nowrap">
                        <Avatar
                          src={d.commander_image}
                          alt=""
                          radius="sm"
                          size={44}
                          imageProps={{ loading: "lazy", style: { objectPosition: "top" } }}
                        />
                        <div style={{ minWidth: 0 }}>
                          <Text fw={600} size="sm" lineClamp={1}>
                            {d.name}
                          </Text>
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            #{d.id} · {commanders}
                            {d.theme ? ` · ${d.theme}` : ""}
                          </Text>
                        </div>
                      </Group>
                    </UnstyledButton>
                  </Table.Td>
                  <Table.Td visibleFrom="sm">
                    <ColorIdentity colors={colorsOf(d)} size="sm" />
                  </Table.Td>
                  <Table.Td ta="right" visibleFrom="md">
                    {d.card_count}
                  </Table.Td>
                  <Table.Td ta="right" visibleFrom="xs">
                    <Text size="sm">{formatPrice(d.total_price)}</Text>
                  </Table.Td>
                  <Table.Td visibleFrom="md">
                    <SourceBadge source={d.source} />
                  </Table.Td>
                  <Table.Td visibleFrom="lg">
                    <Text size="xs" c="dimmed">
                      {formatDate(d.created_at)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Menu position="bottom-end">
                      <Menu.Target>
                        <ActionIcon variant="subtle" aria-label={`Actions for ${d.name}`}>
                          <IconDots size={18} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item component={Link} to={`/decks/${d.id}`}>
                          Open
                        </Menu.Item>
                        <Menu.Item onClick={() => setRenaming(d)}>Rename</Menu.Item>
                        <Menu.Item
                          component="a"
                          href={exportUrl(d.id, "moxfield")}
                          download
                          leftSection={<IconDownload size={14} />}
                        >
                          Download (Moxfield)
                        </Menu.Item>
                        <Menu.Item
                          component="a"
                          href={exportUrl(d.id, "json")}
                          download
                          leftSection={<IconDownload size={14} />}
                        >
                          Download (JSON)
                        </Menu.Item>
                        <Menu.Divider />
                        <Menu.Item color="red" onClick={() => setDeleting(d)}>
                          Delete
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      )}
      {data && pages > 1 && (
        <Group justify="center">
          <Pagination
            total={pages}
            value={page}
            onChange={(p) => update({ page: p > 1 ? String(p) : null })}
            aria-label="Pages"
          />
        </Group>
      )}

      <ImportDeckModal opened={importing} onClose={() => setImporting(false)} />
      <RenameDeckModal deck={renaming} onClose={() => setRenaming(null)} />
      <DeleteDeckModal
        deck={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={() => setSelected((s) => s.filter((id) => id !== deleting?.id))}
      />
    </Stack>
  );
}
