import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Drawer,
  Grid,
  Group,
  Indicator,
  Menu,
  Paper,
  SegmentedControl,
  Select,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { useDebouncedCallback, useDisclosure } from "@mantine/hooks";
import {
  IconAdjustmentsHorizontal,
  IconDots,
  IconLayoutGrid,
  IconList,
  IconSearch,
  IconSortAscending,
  IconSortDescending,
  IconUpload,
} from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { useCollectionCards, useCollectionDetail } from "../api/queries";
import type { CollectionCard, CollectionInfo } from "../api/types";
import { useCardDetail } from "../components/CardDetail";
import { CardTile } from "../components/CardTile";
import { EmptyState, ErrorAlert, PageHeader } from "../components/Feedback";
import { FilterPanel } from "../components/FilterPanel";
import { ColorIdentity, ManaCost } from "../components/ManaCost";
import { ProgressiveGrid, useProgressive } from "../components/ProgressiveGrid";
import { RoleBadge } from "../components/RoleBadge";
import { toggleColor } from "../lib/colors";
import {
  activeFilterCount,
  applyFilters,
  type CardFilters,
  filtersFromParams,
  filtersToParams,
  type SortKey,
} from "../lib/filters";
import { formatPrice, plural } from "../lib/format";
import { patchParams, useUrlParams } from "../lib/useUrlParams";
import { useActiveCollection } from "../state/ActiveCollection";
import {
  DeleteCollectionModal,
  RenameCollectionModal,
  UploadCollectionModal,
} from "./CollectionModals";

const SORTS: { value: SortKey; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "cmc", label: "Mana value" },
  { value: "price", label: "Price" },
  { value: "edhrec", label: "EDHREC rank" },
  { value: "quantity", label: "Copies owned" },
];

function CardListView({
  cards,
  onOpen,
}: {
  cards: CollectionCard[];
  onOpen: (c: CollectionCard) => void;
}) {
  const { visible, sentinel } = useProgressive(cards, 100);
  return (
    <>
      <Table highlightOnHover stickyHeader stickyHeaderOffset={60} verticalSpacing={6}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th ta="right">Cost</Table.Th>
            <Table.Th visibleFrom="md">Type</Table.Th>
            <Table.Th visibleFrom="sm">Role</Table.Th>
            <Table.Th ta="right" visibleFrom="xs">
              Price
            </Table.Th>
            <Table.Th ta="right">Qty</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {visible.map((c) => (
            <Table.Tr key={c.name}>
              <Table.Td>
                <UnstyledButton onClick={() => onOpen(c)}>
                  <Text size="sm" fw={500}>
                    {c.name}
                  </Text>
                </UnstyledButton>
              </Table.Td>
              <Table.Td ta="right">
                <ManaCost cost={c.mana_cost} size="sm" />
              </Table.Td>
              <Table.Td visibleFrom="md">
                <Text size="xs" c="dimmed" lineClamp={1}>
                  {c.type_line}
                </Text>
              </Table.Td>
              <Table.Td visibleFrom="sm">
                <RoleBadge role={c.role} size="xs" />
              </Table.Td>
              <Table.Td ta="right" visibleFrom="xs">
                <Text size="xs">{formatPrice(c.price_usd)}</Text>
              </Table.Td>
              <Table.Td ta="right">{c.quantity}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {sentinel}
    </>
  );
}

function CollectionActions({
  collection,
  onUpload,
  onReplace,
  onRename,
  onDelete,
}: {
  collection: CollectionInfo | null;
  onUpload: () => void;
  onReplace: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  return (
    <>
      <Button leftSection={<IconUpload size={16} />} onClick={onUpload}>
        Upload
      </Button>
      {collection?.editable && (
        <Menu position="bottom-end">
          <Menu.Target>
            <ActionIcon variant="default" size="lg" aria-label="Manage this collection">
              <IconDots size={18} />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item onClick={onRename}>Rename</Menu.Item>
            <Menu.Item onClick={onReplace}>Replace cards…</Menu.Item>
            <Menu.Item color="red" onClick={onDelete}>
              Delete
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      )}
    </>
  );
}

export default function CollectionPage() {
  const { id, collection } = useActiveCollection();
  const detail = useCollectionDetail(id);
  const cards = useCollectionCards(id);
  const [params, updateParams] = useUrlParams();
  const filters = useMemo(() => filtersFromParams(params), [params]);
  const view = params.get("view") === "list" ? "list" : "grid";
  const [search, setSearch] = useState(filters.q);
  const [drawer, { open: openDrawer, close: closeDrawer }] = useDisclosure();
  const [upload, setUpload] = useState<"new" | "replace" | null>(null);
  const [renaming, setRenaming] = useState<CollectionInfo | null>(null);
  const [deleting, setDeleting] = useState<CollectionInfo | null>(null);
  const openCard = useCardDetail();

  // Functional updates: merge each change into the *latest* URL (updates are asynchronous).
  const setFilters = (patch: Partial<CardFilters>) =>
    updateParams((latest) => filtersToParams({ ...filtersFromParams(latest), ...patch }, latest));
  const toggleFilterColor = (color: string) =>
    updateParams((latest) => {
      const f = filtersFromParams(latest);
      return filtersToParams({ ...f, colors: toggleColor(f.colors, color) }, latest);
    });
  const pushSearch = useDebouncedCallback((q: string) => setFilters({ q }), 200);
  const setView = (v: string) =>
    updateParams((latest) => patchParams(latest, { view: v === "list" ? "list" : null }));

  const filtered = useMemo(() => applyFilters(cards.data ?? [], filters), [cards.data, filters]);
  const active = activeFilterCount(filters);
  const open = (c: CollectionCard) => openCard(c.name, { quantity: c.quantity, collection: id });

  const match = detail.data?.match;
  const problems = match ? match.fuzzy.length + match.unmatched.length : 0;

  return (
    <Stack gap="md">
      <PageHeader
        title={collection?.name ?? "Collection"}
        subtitle={
          detail.data ? (
            <>
              {collection?.description} · {plural(detail.data.unique_cards, "card")} (
              {detail.data.copies} copies) · {plural(detail.data.commanders, "commander")}
            </>
          ) : (
            collection?.description
          )
        }
        actions={
          <CollectionActions
            collection={collection}
            onUpload={() => setUpload("new")}
            onReplace={() => setUpload("replace")}
            onRename={() => setRenaming(collection)}
            onDelete={() => setDeleting(collection)}
          />
        }
      />

      {problems > 0 && match && (
        <Alert color="yellow" variant="light" title="Some lines didn't match the card catalog">
          {match.fuzzy.length > 0 && (
            <Text size="sm">
              Corrected: {match.fuzzy.map((f) => `${f.original} → ${f.corrected}`).join(", ")}
            </Text>
          )}
          {match.unmatched.length > 0 && (
            <Text size="sm">Not found (ignored): {match.unmatched.join(", ")}</Text>
          )}
        </Alert>
      )}

      <Paper withBorder p="sm" radius="md">
        <Group gap="sm" wrap="wrap">
          <TextInput
            aria-label="Search cards"
            placeholder="Search name, type or rules text"
            leftSection={<IconSearch size={16} />}
            value={search}
            onChange={(e) => {
              setSearch(e.currentTarget.value);
              pushSearch(e.currentTarget.value);
            }}
            style={{ flex: "1 1 220px" }}
          />
          <Indicator label={active} size={16} disabled={active === 0} hiddenFrom="md">
            <Button
              variant="default"
              leftSection={<IconAdjustmentsHorizontal size={16} />}
              onClick={openDrawer}
              hiddenFrom="md"
            >
              Filters
            </Button>
          </Indicator>
          <Group gap={4} wrap="nowrap">
            <Select
              aria-label="Sort by"
              data={SORTS}
              value={filters.sort}
              onChange={(v) => v && setFilters({ sort: v as SortKey })}
              allowDeselect={false}
              w={150}
            />
            <Tooltip label={filters.dir === "asc" ? "Ascending" : "Descending"}>
              <ActionIcon
                variant="default"
                size="lg"
                aria-label={filters.dir === "asc" ? "Sort descending" : "Sort ascending"}
                onClick={() => setFilters({ dir: filters.dir === "asc" ? "desc" : "asc" })}
              >
                {filters.dir === "asc" ? (
                  <IconSortAscending size={18} />
                ) : (
                  <IconSortDescending size={18} />
                )}
              </ActionIcon>
            </Tooltip>
          </Group>
          <SegmentedControl
            value={view}
            onChange={setView}
            aria-label="Layout"
            data={[
              { value: "grid", label: <IconLayoutGrid size={16} aria-label="Grid" /> },
              { value: "list", label: <IconList size={16} aria-label="List" /> },
            ]}
          />
        </Group>
      </Paper>

      <Grid gap="md">
        <Grid.Col span={{ base: 12, md: 3 }} visibleFrom="md">
          <Paper
            withBorder
            p="md"
            radius="md"
            pos="sticky"
            top={76}
            style={{ maxHeight: "calc(100dvh - 92px)", overflowY: "auto" }}
            aria-label="Filters"
            component="section"
          >
            <FilterPanel value={filters} onChange={setFilters} onToggleColor={toggleFilterColor} />
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          <Stack gap="sm">
            {cards.error && <ErrorAlert error={cards.error} onRetry={() => cards.refetch()} />}
            {cards.isLoading && (
              <Group>
                {Array.from({ length: 6 }, (_, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders
                  <Skeleton key={i} h={220} w={150} radius="md" />
                ))}
              </Group>
            )}
            {cards.data && (
              <Group justify="space-between">
                <Text size="sm" c="dimmed" aria-live="polite">
                  Showing {filtered.length} of {plural(cards.data.length, "card")}
                </Text>
                {filters.colors.length > 0 && (
                  <Group gap={4}>
                    <Badge variant="light">{filters.colorMode}</Badge>
                    <ColorIdentity colors={filters.colors.filter((c) => c !== "C")} size="sm" />
                  </Group>
                )}
              </Group>
            )}
            {cards.data && filtered.length === 0 && (
              <EmptyState
                title="No cards match"
                action={
                  <Button
                    variant="light"
                    onClick={() => {
                      setSearch("");
                      setFilters({
                        q: "",
                        colors: [],
                        types: [],
                        cmc: null,
                        rarities: [],
                        roles: [],
                        maxPrice: null,
                        commandersOnly: false,
                      });
                    }}
                  >
                    Clear search and filters
                  </Button>
                }
              >
                Try fewer filters or another search.
              </EmptyState>
            )}
            {view === "grid" ? (
              <ProgressiveGrid
                items={filtered}
                getKey={(c) => c.name}
                cols={{ base: 2, xs: 3, sm: 4, lg: 5, xl: 6 }}
                spacing="sm"
                render={(c) => <CardTile card={c} quantity={c.quantity} onOpen={() => open(c)} />}
              />
            ) : (
              filtered.length > 0 && <CardListView cards={filtered} onOpen={open} />
            )}
          </Stack>
        </Grid.Col>
      </Grid>

      <Drawer opened={drawer} onClose={closeDrawer} title="Filters" position="bottom" size="85%">
        <FilterPanel value={filters} onChange={setFilters} onToggleColor={toggleFilterColor} />
        <Button fullWidth mt="md" onClick={closeDrawer}>
          Show {plural(filtered.length, "card")}
        </Button>
      </Drawer>

      <UploadCollectionModal
        opened={upload !== null}
        onClose={() => setUpload(null)}
        replace={upload === "replace" ? collection : null}
      />
      <RenameCollectionModal collection={renaming} onClose={() => setRenaming(null)} />
      <DeleteCollectionModal collection={deleting} onClose={() => setDeleting(null)} />
    </Stack>
  );
}
