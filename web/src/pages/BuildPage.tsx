import {
  Alert,
  Badge,
  Box,
  Button,
  Grid,
  Group,
  Loader,
  Modal,
  NumberInput,
  Paper,
  SegmentedControl,
  Select,
  Slider,
  Stack,
  Switch,
  Tabs,
  Text,
  TextInput,
  Title,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle,
  IconArrowsShuffle,
  IconChevronDown,
  IconChevronUp,
  IconDeviceFloppy,
  IconHammer,
  IconRefresh,
} from "@tabler/icons-react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import {
  useBuild,
  useCommanders,
  usePartners,
  useSaveBuild,
  useStatus,
  useVocabulary,
} from "../api/queries";
import type { BuildResponse, CommanderEntry } from "../api/types";
import { useCardDetail } from "../components/CardDetail";
import { CardImage } from "../components/CardImage";
import { ColorPicker } from "../components/ColorPicker";
import { DeckCardList } from "../components/DeckCardList";
import { StatSummary } from "../components/DeckStatsPanel";
import { ExportMenu } from "../components/ExportMenu";
import { EmptyState, ErrorAlert, PageHeader } from "../components/Feedback";
import { ColorIdentity } from "../components/ManaCost";
import { NoticeList } from "../components/NoticeList";
import { ThemeSelect } from "../components/ThemeSelect";
import { TokenList } from "../components/TokenList";
import {
  type BuildForm,
  formFromBuildParams,
  formFromSearch,
  formProblem,
  formToRequest,
  formToSearch,
} from "../lib/buildForm";
import { toggleColor } from "../lib/colors";
import { formatPrice } from "../lib/format";
import { useUrlParams } from "../lib/useUrlParams";
import { useActiveCollection } from "../state/ActiveCollection";
import classes from "./BuildPage.module.css";

const DeckStatsPanel = lazy(() =>
  import("../components/DeckStatsPanel").then((m) => ({ default: m.DeckStatsPanel })),
);

function randomSeed() {
  return Math.floor(Math.random() * 2 ** 31);
}

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <Stack gap={4}>
      <Text size="sm" fw={500}>
        {label}
      </Text>
      {children}
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Stack>
  );
}

function commanderOption(entry: CommanderEntry) {
  return { value: entry.card.name, label: entry.card.name, colors: entry.card.color_identity };
}

function BuildOptions({
  form,
  onChange,
  onToggleColor,
  onBuild,
  building,
}: {
  form: BuildForm;
  onChange: (patch: Partial<BuildForm>) => void;
  onToggleColor: (color: string) => void;
  onBuild: () => void;
  building: boolean;
}) {
  const commanders = useCommanders(form.collection);
  const { data: vocab } = useVocabulary();
  const { data: status } = useStatus();
  const entry = commanders.data?.find((c) => c.card.name === form.commander) ?? null;
  const partners = usePartners(form.collection, form.commander, Boolean(entry?.can_take_partner));
  const set = <K extends keyof BuildForm>(key: K, value: BuildForm[K]) =>
    onChange({ [key]: value } as Partial<BuildForm>);
  const problem = formProblem(form);

  const commanderData = useMemo(
    () => (commanders.data ?? []).map(commanderOption),
    [commanders.data],
  );
  const colorsByName = useMemo(
    () => new Map(commanderData.map((o) => [o.value, o.colors] as const)),
    [commanderData],
  );
  const bracketInfo = form.bracket ? vocab?.brackets[String(form.bracket)] : null;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!problem) onBuild();
      }}
    >
      <Stack gap="md">
        <SegmentedControl
          fullWidth
          value={form.mode}
          onChange={(v) => onChange({ mode: v as BuildForm["mode"] })}
          aria-label="How to choose the commander"
          data={[
            { value: "commander", label: "Choose commander" },
            { value: "auto", label: "Auto-pick" },
          ]}
        />

        {form.mode === "commander" ? (
          <>
            <Select
              label="Commander"
              placeholder={
                commanders.isLoading ? "Loading commanders…" : "Pick a commander you own"
              }
              searchable
              data={commanderData}
              value={form.commander}
              onChange={(v) => onChange({ commander: v, partner: null })}
              nothingFoundMessage="No such commander in this collection"
              renderOption={({ option }) => (
                <Group gap={6} wrap="nowrap">
                  <ColorIdentity colors={colorsByName.get(option.value) ?? []} size="sm" />
                  <span>{option.label}</span>
                </Group>
              )}
              error={commanders.error ? "Couldn't load commanders" : undefined}
            />
            {entry?.can_take_partner && (
              <Select
                label="Partner (second commander)"
                placeholder={
                  partners.data?.length ? "Optional" : "No legal partner in this collection"
                }
                data={(partners.data ?? []).map((p) => p.name)}
                value={form.partner}
                onChange={(v) => set("partner", v)}
                clearable
                disabled={!partners.data?.length}
                description={entry.partner_tags.join(", ")}
              />
            )}
          </>
        ) : (
          <Field label="Colors" hint="The commander will be within these colors.">
            <ColorPicker value={form.colors} onToggle={onToggleColor} label="Deck colors" />
          </Field>
        )}

        <ThemeSelect
          label="Theme"
          placeholder={form.mode === "auto" ? "Archetype or tribe" : "Optional"}
          value={form.theme}
          onChange={(v) => set("theme", v)}
          description={
            form.mode === "commander" ? "Lean the deck into an archetype or tribe." : undefined
          }
        />

        <Field label={`Lands: ${form.lands}`}>
          <Slider
            min={28}
            max={45}
            value={form.lands}
            onChange={(v) => set("lands", v)}
            marks={[{ value: 33 }, { value: 37, label: "37" }, { value: 41 }]}
            aria-label="Number of lands"
            thumbLabel="Number of lands"
            mb="sm"
          />
        </Field>

        <Field
          label={`Variety: ${form.variety.toFixed(1)}`}
          hint={
            form.variety === 0
              ? "0 = always the same strongest deck."
              : "Higher = more different decks per build."
          }
        >
          <Slider
            min={0}
            max={1}
            step={0.1}
            value={form.variety}
            onChange={(v) => set("variety", v)}
            aria-label="Variety"
            thumbLabel="Variety"
            label={(v) => v.toFixed(1)}
          />
        </Field>
        <NumberInput
          label="Seed"
          description="Same seed + same settings = same deck."
          placeholder="Random"
          value={form.seed ?? ""}
          onChange={(v) => set("seed", v === "" ? null : Number(v))}
          allowDecimal={false}
          min={0}
          rightSection={
            <Tooltip label="New random seed">
              <UnstyledButton
                aria-label="New random seed"
                onClick={() => set("seed", randomSeed())}
                px={6}
              >
                <IconArrowsShuffle size={16} />
              </UnstyledButton>
            </Tooltip>
          }
        />

        <NumberInput
          label="Budget"
          description="Whole deck, commander included (USD)."
          placeholder="No limit"
          prefix="$"
          min={0}
          decimalScale={2}
          value={form.budget ?? ""}
          onChange={(v) => set("budget", v === "" ? null : Number(v))}
        />

        <Field label="Power bracket" hint={bracketInfo ?? "Any: no power restrictions."}>
          <SegmentedControl
            fullWidth
            size="xs"
            value={form.bracket ? String(form.bracket) : "any"}
            onChange={(v) => set("bracket", v === "any" ? null : Number(v))}
            aria-label="Power bracket"
            data={["any", "1", "2", "3", "4", "5"].map((v) => ({
              value: v,
              label: v === "any" ? "Any" : v,
            }))}
          />
          {form.bracket !== null && form.bracket < 5 && status?.offline && (
            <Text size="xs" style={{ color: "var(--mantine-color-yellow-light-color)" }}>
              Offline: game changers, extra turns and land denial are checked; combos are not.
            </Text>
          )}
        </Field>

        <Button
          type="submit"
          size="md"
          loading={building}
          leftSection={<IconHammer size={18} />}
          disabled={Boolean(problem)}
          aria-describedby={problem ? "build-problem" : undefined}
        >
          Build deck
        </Button>
        {problem && (
          <Text size="xs" c="dimmed" ta="center" id="build-problem">
            {problem}
          </Text>
        )}
      </Stack>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------

function SaveModal({
  build,
  opened,
  onClose,
}: {
  build: BuildResponse;
  opened: boolean;
  onClose: () => void;
}) {
  const deck = build.result.deck;
  const defaultName = [deck.commander.name, deck.partner?.name].filter(Boolean).join(" + ");
  const [name, setName] = useState(defaultName);
  const save = useSaveBuild();
  const navigate = useNavigate();
  useEffect(() => {
    if (opened) setName(defaultName);
  }, [opened, defaultName]);
  return (
    <Modal opened={opened} onClose={onClose} title="Save deck">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const saved = await save.mutateAsync({
            build_id: build.build_id,
            name: name.trim() || null,
          });
          notifications.show({
            color: "teal",
            message: `Saved "${saved.name}" (deck #${saved.id})`,
          });
          onClose();
          navigate(`/decks/${saved.id}`);
        }}
      >
        <Stack>
          <TextInput
            label="Name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            data-autofocus
            maxLength={200}
          />
          {save.error && <ErrorAlert error={save.error} />}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              loading={save.isPending}
              leftSection={<IconDeviceFloppy size={16} />}
            >
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

function warningsOf(build: BuildResponse) {
  return build.result.report.notices.filter((n) => n.level === "warning" || n.level === "error");
}

function BuildResult({
  build,
  onRebuild,
  onReroll,
  rebuilding,
}: {
  build: BuildResponse;
  onRebuild: () => void;
  onReroll: () => void;
  rebuilding: boolean;
}) {
  const { deck, stats, tokens, report, params } = build.result;
  const [saving, setSaving] = useState(false);
  const [details, setDetails] = useState(false);
  const openCard = useCardDetail();
  const commanders = [deck.commander, ...(deck.partner ? [deck.partner] : [])];
  const warnings = warningsOf(build);

  return (
    <Stack gap="md">
      <Paper withBorder p="md" radius="md">
        <Group align="flex-start" wrap="nowrap" gap="md">
          {commanders.map((c) => (
            <UnstyledButton
              key={c.name}
              w={{ base: 72, sm: 110 }}
              onClick={() => openCard(c.name)}
              aria-label={`${c.name} — show details`}
              style={{ flex: "none" }}
            >
              <CardImage name={c.name} images={c.images} radius="sm" />
            </UnstyledButton>
          ))}
          <Stack gap={6} style={{ minWidth: 0, flex: 1 }}>
            <Title order={2} fz={{ base: "lg", sm: "xl" }}>
              {commanders.map((c) => c.name).join(" + ")}
            </Title>
            <Group gap={6}>
              <ColorIdentity
                colors={[...new Set(commanders.flatMap((c) => c.color_identity))]}
                size="sm"
              />
              {report.autopick.commander_auto && <Badge variant="light">Auto-picked</Badge>}
              {report.theme && <Badge variant="light">Theme: {report.theme}</Badge>}
              {report.seed !== null && (
                <Badge variant="light" color="gray">
                  Seed {report.seed}
                </Badge>
              )}
              {report.bracket && (
                <Badge
                  variant="light"
                  color={report.bracket.mode === "offline" ? "yellow" : "teal"}
                >
                  Bracket {report.bracket.bracket}
                  {report.bracket.mode === "offline" ? " (offline rules)" : ""}
                </Badge>
              )}
              {report.budget && (
                <Badge variant="light" color={report.budget.met ? "teal" : "red"}>
                  Budget {formatPrice(report.budget.final_price)} /{" "}
                  {formatPrice(report.budget.budget)}
                </Badge>
              )}
            </Group>
            <Group gap="xs" mt={4}>
              <Button leftSection={<IconDeviceFloppy size={16} />} onClick={() => setSaving(true)}>
                Save
              </Button>
              <Tooltip label="Build again with the same settings and seed (same deck)">
                <Button
                  variant="default"
                  leftSection={<IconRefresh size={16} />}
                  onClick={onRebuild}
                  loading={rebuilding}
                >
                  Rebuild
                </Button>
              </Tooltip>
              <Tooltip label="New random seed (with some variety) for a different deck">
                <Button
                  variant="default"
                  leftSection={<IconArrowsShuffle size={16} />}
                  onClick={onReroll}
                  disabled={rebuilding}
                >
                  Re-roll
                </Button>
              </Tooltip>
              <ExportMenu deck={deck} />
            </Group>
          </Stack>
        </Group>
      </Paper>

      {warnings.length > 0 && (
        <Alert color="yellow" variant="light" icon={<IconAlertTriangle />} title="Heads-up">
          <NoticeList notices={warnings} />
        </Alert>
      )}

      <StatSummary stats={stats} />

      <Tabs defaultValue="cards" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="cards">Cards</Tabs.Tab>
          <Tabs.Tab value="stats">Stats</Tabs.Tab>
          <Tabs.Tab value="tokens">Tokens ({tokens.length})</Tabs.Tab>
          <Tabs.Tab value="log">Build log</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="cards" pt="md">
          <DeckCardList deck={deck} />
        </Tabs.Panel>
        <Tabs.Panel value="stats" pt="md">
          <Suspense fallback={<Loader />}>
            <DeckStatsPanel stats={stats} />
          </Suspense>
        </Tabs.Panel>
        <Tabs.Panel value="tokens" pt="md">
          <TokenList tokens={tokens} />
        </Tabs.Panel>
        <Tabs.Panel value="log" pt="md">
          <Switch
            label="Show technical details"
            checked={details}
            onChange={(e) => setDetails(e.currentTarget.checked)}
            mb="sm"
            size="xs"
          />
          <NoticeList notices={report.notices} showDetails={details} />
          <Text size="xs" c="dimmed" mt="md">
            Collection: {report.match?.source} · {report.candidate_count} candidate cards · lands{" "}
            {params.lands}
          </Text>
        </Tabs.Panel>
      </Tabs>

      <SaveModal build={build} opened={saving} onClose={() => setSaving(false)} />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BuildPage() {
  const { id: activeId, collections, setId } = useActiveCollection();
  const [params, updateParams] = useUrlParams();
  const build = useBuild();
  const form = useMemo(() => formFromSearch(params, activeId ?? ""), [params, activeId]);
  const resultRef = useRef<HTMLDivElement>(null);
  // Read synchronously on the first render: phones collapse the options after a build.
  const narrow = useMediaQuery("(max-width: 62em)", false, { getInitialValueInEffect: false });
  const [optionsOpen, setOptionsOpen] = useState(true);
  const autoRan = useRef(false);
  const requestedCollection = params.get("collection");
  const resetBuild = build.reset;

  // A saved build link chooses its original collection in the header as well.
  useEffect(() => {
    if (
      requestedCollection &&
      requestedCollection !== activeId &&
      collections.some((c) => c.id === requestedCollection)
    ) {
      setId(requestedCollection);
    }
  }, [requestedCollection, activeId, collections, setId]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: discard results when the collection changes
  useEffect(() => {
    resetBuild();
    setOptionsOpen(true);
    autoRan.current = false;
  }, [form.collection, resetBuild]);

  // Merge each change into the latest URL state (URL updates are asynchronous).
  const patchForm = (patch: Partial<BuildForm>) =>
    updateParams((latest) => formToSearch({ ...formFromSearch(latest, activeId ?? ""), ...patch }));

  const run = (f: BuildForm) => {
    updateParams(() => formToSearch(f));
    build.mutate(formToRequest(f), {
      onSuccess: () => {
        if (narrow) {
          setOptionsOpen(false);
          requestAnimationFrame(() => resultRef.current?.scrollIntoView({ block: "start" }));
        }
      },
    });
  };

  // Links such as "Rebuild with these settings" carry run=1: build once on arrival.
  // biome-ignore lint/correctness/useExhaustiveDependencies: run once per arrival
  useEffect(() => {
    if (params.get("run") === "1" && form.collection && !autoRan.current && !formProblem(form)) {
      autoRan.current = true;
      run(form);
    }
  }, [params, form]);

  const rebuild = () => {
    const resolved = build.data?.result.params;
    if (!resolved) return;
    run(formFromBuildParams(resolved));
  };
  const reroll = () =>
    run({ ...form, seed: randomSeed(), variety: form.variety > 0 ? form.variety : 0.5 });

  return (
    <Stack gap="md">
      <PageHeader
        title="Build a deck"
        subtitle="From the cards in the active collection. Nothing is saved until you press Save."
      />
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper withBorder p="md" radius="md" className={classes.options}>
            {narrow && build.data && (
              <Button
                variant="subtle"
                fullWidth
                justify="space-between"
                rightSection={
                  optionsOpen ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />
                }
                onClick={() => setOptionsOpen((o) => !o)}
                aria-expanded={optionsOpen}
                mb={optionsOpen ? "sm" : 0}
              >
                {optionsOpen ? "Hide options" : "Change options"}
              </Button>
            )}
            {!optionsOpen && narrow && build.data ? null : form.collection ? (
              <BuildOptions
                form={form}
                onChange={patchForm}
                onToggleColor={(color) =>
                  updateParams((latest) => {
                    const f = formFromSearch(latest, activeId ?? "");
                    return formToSearch({ ...f, colors: toggleColor(f.colors, color) });
                  })
                }
                onBuild={() => run(form)}
                building={build.isPending}
              />
            ) : (
              <Loader />
            )}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Box ref={resultRef} style={{ scrollMarginTop: 76 }}>
            {build.error && <ErrorAlert error={build.error} />}
            {build.isPending && !build.data && (
              <Group justify="center" py="xl">
                <Loader />
                <Text c="dimmed">Building…</Text>
              </Group>
            )}
            {build.data ? (
              <BuildResult
                build={build.data}
                onRebuild={rebuild}
                onReroll={reroll}
                rebuilding={build.isPending}
              />
            ) : (
              !build.isPending &&
              !build.error && (
                <EmptyState title="No deck yet" icon={<IconHammer />}>
                  Choose a commander — or let CommanderAI pick one for a theme or colors — then
                  press Build deck.
                </EmptyState>
              )
            )}
          </Box>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
