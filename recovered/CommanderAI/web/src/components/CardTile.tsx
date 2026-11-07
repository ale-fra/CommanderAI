import { Badge, Group, Paper, Stack, Text, UnstyledButton } from "@mantine/core";
import type { CardSummary } from "../api/types";
import { formatPrice } from "../lib/format";
import { CardImage } from "./CardImage";
import classes from "./CardTile.module.css";
import { ManaCost } from "./ManaCost";

interface CardTileProps {
  card: CardSummary;
  quantity?: number;
  onOpen?: (name: string) => void;
  showPrice?: boolean;
}

export function CardTile({ card, quantity, onOpen, showPrice = true }: CardTileProps) {
  return (
    <UnstyledButton className={classes.tile} onClick={() => onOpen?.(card.name)}>
      <Paper withBorder radius="md" p={6} className={classes.paper}>
        <div className={classes.imageWrap}>
          <CardImage name={card.name} images={card.images} radius="sm" decorative />
          {quantity !== undefined && quantity > 1 && (
            <Badge className={classes.qty} size="sm" variant="filled" color="dark">
              ×{quantity}
            </Badge>
          )}
        </div>
        <Stack gap={2} mt={6} px={2}>
          <Text size="sm" fw={600} lineClamp={2} title={card.name}>
            {card.name}
          </Text>
          <Group justify="space-between" gap={4} wrap="nowrap">
            <ManaCost cost={card.mana_cost} size="sm" />
            {showPrice && (
              <Text size="xs" c="dimmed" style={{ whiteSpace: "nowrap" }}>
                {formatPrice(card.price_usd)}
              </Text>
            )}
          </Group>
        </Stack>
      </Paper>
    </UnstyledButton>
  );
}
