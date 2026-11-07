import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  List,
  Loader,
  Menu,
  Paper,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Textarea,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCircleCheck, IconDots, IconRefresh } from "@tabler/icons-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useDeck, useUpdateDeck } from "../api/queries";
import type { DeckDetail } from "../api/types";
import { useCardDetail } from "../components/CardDetail";
import { CardImage } from "../components/CardImage";
import { DeckCardList } from "../components/DeckCardList";
import { StatSummary } from "../components/DeckStatsPanel";
import { ExportMenu } from "../components/ExportMenu";
import { EmptyState, ErrorAlert } from "../components/Feedback";
import { ColorIdentity } from "../components/ManaCost";
import { NoticeList } from "../components/NoticeList";
import { TokenList } from "../components/TokenList";
import { rebuildHref } from "../lib/buildForm";
import { formatDate, formatPrice } from "../lib/format";
import { DeleteDeckModal, RenameDeckModal } from "./DeckModals";
import { SourceBadge } from "./DecksPage";

const DeckStatsPanel = lazy(() =>
  import("../components/DeckStatsPanel").then((m) => ({ default: m.DeckStatsPanel })),
);

function BuildInfo({ deck }: { deck: DeckDetail }) {
  const { report, params } = deck;
  if (!report) {
    return (
      <Text c="dimmed" size="sm">
        This deck was {deck.source === "legacy" ? "migrated from a legacy file" : "imported"}; it
        has no build information.
      </Text>
    );
  }
  const rows: [string, string][] = [
    ["Collection", report.match?.source ?? deck.collection_source ?? "—"],
    ["Theme", report.theme ?? "—"],
    ["Colors filter", report.color_filter?.join("") ?? "—"],
    [
      "Seed",
      report.seed !== null
        ? `${report.seed} (variety ${report.variety.toFixed(2)})`
        : "none (deterministic)",
    ],
    ["Lands", String(report.lands)],
    [
      "Budget",
      report.budget
        ? `${formatPrice(report.budget.final_price)} of ${formatPrice(report.budget.budget)}`
        : "—",
    ],
    ["Bracket", report.bracket ? `${report.bracket.bracket} (${report.bracket.mode} rules)` : "—"],
    ["Commander", report.autopick.commander_auto ? "auto-picked" : "chosen"],
  ];
  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
        {rows.map(([k, v]) => (
          <Group key={k} justify="space-between" wrap="nowrap">
            <Text size="sm" c="dimmed">
              {k}
            </Text>
            <Text size="sm" ta="right">
              {v}
            </Text>
          </Group>
        ))}
      </SimpleGrid>
      {params && (
        <Button
          component={Link}
          to={rebuildHref(params)}
          variant="light"
          leftSection={<IconRefresh size={16} />}
          w="fit-content"
        >
          Rebuild with these settings
        </Button>
      )}
      <div>
        <Title order={3} fz="sm" mb="xs">
          Build log
        </Title>
        <NoticeList notices={report.notices} showDetails={false} />
      </div>
    </Stack>
  );
}

function Notes({ deck }: { deck: DeckDetail }) {
  const [notes, setNotes] = useState(deck.notes);
  const update = useUpdateDeck();
  useEffect(() => setNotes(deck.notes), [deck.notes]);
  return (
    <Stack gap="xs">
      <Textarea
        label="Notes"
        autosize
        minRows={4}
        value={notes}
        onChange={(e) => setNotes(e.currentTarget.value)}
        placeholder="Ideas, swaps to try, how it played…"
        maxLength={10000}
      />
      <Group>
        <Button
          size="xs"
          disabled={notes === deck.notes}
          loading={update.isPending}
          onClick={async () => {
            await update.mutateAsync({ id: deck.id, notes });
            notifications.show({ color: "teal", message: "Notes saved" });
          }}
        >
          Save notes
        </Button>
      </Group>
      {update.error && <ErrorAlert error={update.error} />}
    </Stack>
  );
}

export default function DeckDetailPage() {
  const { id } = useParams();
  const deckId = Number(id);
  const { data: deck, error, isLoading } = useDeck(Number.isInteger(deckId) ? deckId : null);
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const openCard = useCardDetail();
  const navigate = useNavigate();

  if (!Number.isInteger(deckId)) return <EmptyState title="Deck not found" />;
  if (isLoading) return <Loader />;
  if (error) return <ErrorAlert error={error} />;
  if (!deck) return null;

  const commanders = [deck.deck.commander, ...(deck.deck.partner ? [deck.deck.partner] : [])];
  const valid = deck.validation_errors.length === 0;

  return (
    <Stack gap="md">
      <Paper withBorder p="md" radius="md">
        <Group align="flex-start" wrap="nowrap" gap="md">
          {commanders.map((c) => (
            <UnstyledButton
              key={c.name}
              w={{ base: 72, sm: 110 }}
              style={{ flex: "none" }}
              onClick={() => openCard(c.name)}
              aria-label={`${c.name} — show details`}
            >
              <CardImage name={c.name} images={c.images} radius="sm" />
            </UnstyledButton>
          ))}
          <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <div style={{ minWidth: 0 }}>
                <Title order={2} fz={{ base: "lg", sm: "xl" }}>
                  {deck.name}
                </Title>
                <Text size="sm" c="dimmed">
                  {commanders.map((c) => c.name).join(" + ")}
                </Text>
              </div>
              <Menu position="bottom-end">
                <Menu.Target>
                  <ActionIcon variant="default" size="lg" aria-label="Deck actions">
                    <IconDots size={18} />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item onClick={() => setRenaming(true)}>Rename</Menu.Item>
                  {deck.params && (
                    <Menu.Item component={Link} to={rebuildHref(deck.params)}>
                      Rebuild with these settings
                    </Menu.Item>
                  )}
                  <Menu.Divider />
                  <Menu.Item color="red" onClick={() => setDeleting(true)}>
                    Delete
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
            <Group gap={6}>
              <ColorIdentity
                colors={[...new Set(commanders.flatMap((c) => c.color_identity))]}
                size="sm"
              />
              <SourceBadge source={deck.source} />
              {deck.report?.theme && <Badge variant="light">Theme: {deck.report.theme}</Badge>}
              <Badge variant="light" color={valid ? "teal" : "red"}>
                {valid ? "Legal" : `${deck.validation_errors.length} problem(s)`}
              </Badge>
            </Group>
            <Text size="xs" c="dimmed">
              #{deck.id} · created {formatDate(deck.created_at)} UTC
              {deck.export_path ? ` · file ${deck.export_path.split(/[\\/]/).pop()}` : ""}
            </Text>
            <Group gap="xs" mt={4}>
              <ExportMenu deckId={deck.id} deck={deck.deck} />
            </Group>
          </Stack>
        </Group>
      </Paper>

      <StatSummary stats={deck.stats} />

      <Tabs defaultValue="cards" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="cards">Cards</Tabs.Tab>
          <Tabs.Tab value="stats">Stats</Tabs.Tab>
          <Tabs.Tab value="tokens">Tokens ({deck.tokens.length})</Tabs.Tab>
          <Tabs.Tab value="validation">Legality</Tabs.Tab>
          <Tabs.Tab value="build">Build info</Tabs.Tab>
          <Tabs.Tab value="notes">Notes</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="cards" pt="md">
          <DeckCardList deck={deck.deck} />
        </Tabs.Panel>
        <Tabs.Panel value="stats" pt="md">
          <Suspense fallback={<Loader />}>
            <DeckStatsPanel stats={deck.stats} />
          </Suspense>
        </Tabs.Panel>
        <Tabs.Panel value="tokens" pt="md">
          <TokenList tokens={deck.tokens} />
        </Tabs.Panel>
        <Tabs.Panel value="validation" pt="md">
          {valid ? (
            <Alert
              color="teal"
              variant="light"
              icon={<IconCircleCheck />}
              title="This deck is legal"
            >
              {deck.stats.card_count} cards, every card within the commander's color identity,
              singleton (basic lands excepted).
            </Alert>
          ) : (
            <Alert color="red" variant="light" title="Deck-construction problems">
              <List size="sm">
                {deck.validation_errors.map((e) => (
                  <List.Item key={e}>{e}</List.Item>
                ))}
              </List>
            </Alert>
          )}
        </Tabs.Panel>
        <Tabs.Panel value="build" pt="md">
          <BuildInfo deck={deck} />
        </Tabs.Panel>
        <Tabs.Panel value="notes" pt="md">
          <Notes deck={deck} />
        </Tabs.Panel>
      </Tabs>

      <RenameDeckModal deck={renaming ? deck : null} onClose={() => setRenaming(false)} />
      <DeleteDeckModal
        deck={deleting ? deck : null}
        onClose={() => setDeleting(false)}
        onDeleted={() => navigate("/decks")}
      />
    </Stack>
  );
}
