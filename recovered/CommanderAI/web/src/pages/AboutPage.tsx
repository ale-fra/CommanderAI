import { Anchor, Badge, Group, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useStatus } from "../api/queries";
import { ErrorAlert, PageHeader } from "../components/Feedback";
import { formatDate } from "../lib/format";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Group justify="space-between" wrap="nowrap" gap="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" ta="right">
        {children}
      </Text>
    </Group>
  );
}

export default function AboutPage() {
  const { data, error } = useStatus();
  return (
    <Stack maw={900}>
      <PageHeader
        title="About CommanderAI"
        subtitle="Build Commander decks from the cards you own."
      />
      {error && <ErrorAlert error={error} />}
      {data && (
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Paper withBorder p="md" radius="md">
            <Title order={3} fz="md" mb="sm">
              System
            </Title>
            <Stack gap={6}>
              <Row label="Version">{data.version}</Row>
              <Row label="Mode">
                <Badge variant="light" color={data.offline ? "gray" : "teal"}>
                  {data.offline ? "Offline" : "Online"}
                </Badge>
              </Row>
              <Row label="Card catalog">{data.catalog.cards} cards</Row>
              <Row label="Catalog snapshot">
                {data.catalog.snapshot ? formatDate(data.catalog.snapshot) : "—"}
              </Row>
            </Stack>
          </Paper>
          <Paper withBorder p="md" radius="md">
            <Title order={3} fz="md" mb="sm">
              Your data
            </Title>
            <Stack gap={6}>
              <Row label="Saved decks">{data.database.decks}</Row>
              <Row label="Uploaded collections">{data.database.collections}</Row>
              <Row label="Default collection">{data.default_collection ?? "—"}</Row>
              {data.migration && (
                <Row label="Imported legacy deck files">
                  {data.migration.imported}
                  {data.migration.failed > 0 && ` (${data.migration.failed} not decks)`}
                </Row>
              )}
            </Stack>
          </Paper>
        </SimpleGrid>
      )}
      <Text size="sm" c="dimmed">
        Offline mode: power brackets use local rules (game changers, extra turns, mass land denial);
        combos are not checked. Card prices come from the catalog snapshot and may be out of date.
        Mana symbols: the Mana font by Andrew Gioia (SIL OFL). API reference:{" "}
        <Anchor href="/api/docs" underline="always">
          /api/docs
        </Anchor>
        .
      </Text>
    </Stack>
  );
}
