import { Badge, Group, Paper, SimpleGrid, Text } from "@mantine/core";
import type { Token } from "../api/types";
import { EmptyState } from "./Feedback";

export function TokenList({ tokens }: { tokens: Token[] }) {
  if (tokens.length === 0)
    return <EmptyState title="No tokens">No card in this deck creates tokens.</EmptyState>;
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
      {tokens.map((t) => (
        <Paper key={`${t.name}|${t.power}/${t.toughness}`} withBorder p="sm" radius="md">
          <Group justify="space-between" wrap="nowrap" align="flex-start">
            <div style={{ minWidth: 0 }}>
              <Text fw={600}>{t.name}</Text>
              <Text size="xs" c="dimmed">
                {[t.colors.join(" "), t.types].filter(Boolean).join(" ") || "Token"}
              </Text>
            </div>
            {t.power && t.toughness && (
              <Badge variant="light" size="lg">
                {t.power}/{t.toughness}
              </Badge>
            )}
          </Group>
          {t.keywords.length > 0 && (
            <Group gap={4} mt={6}>
              {t.keywords.map((k) => (
                <Badge key={k} size="xs" variant="outline">
                  {k}
                </Badge>
              ))}
            </Group>
          )}
          <Text size="xs" mt={6}>
            <Text span c="dimmed">
              Created by:{" "}
            </Text>
            {t.created_by.join(", ")}
          </Text>
        </Paper>
      ))}
    </SimpleGrid>
  );
}
