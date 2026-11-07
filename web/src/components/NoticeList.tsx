import { List, Stack, Text, ThemeIcon } from "@mantine/core";
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleX,
  IconInfoCircle,
  IconPoint,
} from "@tabler/icons-react";
import type { Notice } from "../api/types";

const LEVELS = {
  info: { color: "blue", icon: IconInfoCircle },
  detail: { color: "gray", icon: IconPoint },
  success: { color: "teal", icon: IconCircleCheck },
  warning: { color: "yellow", icon: IconAlertTriangle },
  error: { color: "red", icon: IconCircleX },
} as const;

type Item = { name?: string; reason?: string; cards?: string[] };

/** Extra lines carried in a notice's data (excluded cards, combos, validation errors…). */
function noticeItems(n: Notice): string[] {
  const d = n.data as Record<string, unknown>;
  if (Array.isArray(d.cards) && n.code === "bracket.excluded_cards")
    return (d.cards as Item[]).map((c) => `${c.name} — ${c.reason}`);
  if (Array.isArray(d.combos))
    return (d.combos as Item[]).map((c) => `${(c.cards ?? []).join(" + ")} — ${c.reason}`);
  if (Array.isArray(d.errors)) return d.errors as string[];
  return [];
}

/** The build log. `detail` notices can be hidden for a compact view. */
export function NoticeList({
  notices,
  showDetails = true,
}: {
  notices: Notice[];
  showDetails?: boolean;
}) {
  const shown = showDetails ? notices : notices.filter((n) => n.level !== "detail");
  return (
    <Stack gap={6} component="ul" style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {shown.map((n, i) => {
        const { color, icon: Icon } = LEVELS[n.level];
        const items = noticeItems(n);
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: a log can repeat the same code; order is fixed
          <li key={`${n.code}-${i}`} data-level={n.level} data-code={n.code}>
            <Text
              size="sm"
              c={n.level === "detail" ? "dimmed" : undefined}
              style={{ display: "flex", gap: 8 }}
            >
              <ThemeIcon
                size={20}
                variant="light"
                color={color}
                radius="xl"
                style={{ flex: "none" }}
              >
                <Icon size={14} />
              </ThemeIcon>
              <span>{n.message}</span>
            </Text>
            {items.length > 0 && (
              <List size="xs" ml={36} mt={2}>
                {items.map((item) => (
                  <List.Item key={item}>{item}</List.Item>
                ))}
              </List>
            )}
          </li>
        );
      })}
    </Stack>
  );
}
