import { Badge, type BadgeProps } from "@mantine/core";
import type { DeckSlot } from "../api/types";
import { titleCase } from "../lib/format";

export const ROLE_COLORS: Record<DeckSlot, string> = {
  RAMP: "green",
  DRAW: "blue",
  REMOVAL: "red",
  WIPE: "orange",
  THREAT: "grape",
  UTILITY: "cyan",
  LAND: "gray",
};

export const ROLE_ORDER: DeckSlot[] = [
  "RAMP",
  "DRAW",
  "REMOVAL",
  "WIPE",
  "THREAT",
  "UTILITY",
  "LAND",
];

export function roleLabel(role: DeckSlot): string {
  return titleCase(role);
}

export function RoleBadge({ role, ...props }: { role: DeckSlot } & BadgeProps) {
  return (
    <Badge color={ROLE_COLORS[role]} variant="light" {...props}>
      {roleLabel(role)}
    </Badge>
  );
}
