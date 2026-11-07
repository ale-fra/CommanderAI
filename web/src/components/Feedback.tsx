import { Alert, Button, Center, Group, List, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconAlertTriangle, IconMoodEmpty } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { friendlyError } from "../lib/errors";

export function ErrorAlert({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const f = friendlyError(error);
  return (
    <Alert color="red" variant="light" icon={<IconAlertTriangle />} title={f.title} role="alert">
      <Text size="sm">{f.message}</Text>
      {f.details.length > 0 && (
        <List size="xs" mt={4}>
          {f.details.map((d) => (
            <List.Item key={d}>{d}</List.Item>
          ))}
        </List>
      )}
      {onRetry && (
        <Button size="xs" variant="light" color="red" mt="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </Alert>
  );
}

export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <Center py="xl">
      <Stack align="center" gap="xs" maw={420} ta="center">
        <ThemeIcon size={48} radius="xl" variant="light" color="gray">
          {icon ?? <IconMoodEmpty />}
        </ThemeIcon>
        <Title order={3} fz="lg">
          {title}
        </Title>
        {children && (
          <Text c="dimmed" size="sm">
            {children}
          </Text>
        )}
        {action}
      </Stack>
    </Center>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <Group justify="space-between" align="flex-start" gap="sm" mb="md">
      <div style={{ minWidth: 0 }}>
        <Title order={2}>{title}</Title>
        {subtitle && (
          <Text c="dimmed" size="sm" mt={2}>
            {subtitle}
          </Text>
        )}
      </div>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}
