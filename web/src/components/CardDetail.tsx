import {
  Badge,
  Button,
  Grid,
  Group,
  Loader,
  Modal,
  Stack,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { IconHammer, IconRefresh } from "@tabler/icons-react";
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useCard } from "../api/queries";
import { formatPrice } from "../lib/format";
import { CardImage } from "./CardImage";
import { ErrorAlert } from "./Feedback";
import { ManaCost } from "./ManaCost";
import { RoleBadge } from "./RoleBadge";

interface OpenOptions {
  quantity?: number;
  /** Collection to use for "Build with this commander". */
  collection?: string | null;
}

const Context = createContext<(name: string, options?: OpenOptions) => void>(() => {});

export const useCardDetail = () => useContext(Context);

/** Renders rules text keeping line breaks and showing {X} symbols as mana icons. */
export function OracleText({ text }: { text: string }) {
  return (
    <Stack gap={6}>
      {text.split("\n").map((line, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: static paragraphs of one card
        <Text key={i} size="sm" style={{ whiteSpace: "pre-wrap" }}>
          {line.split(/(\{[^}]+\})/).map((part, j) =>
            /^\{[^}]+\}$/.test(part) ? (
              // biome-ignore lint/suspicious/noArrayIndexKey: static symbol positions
              <ManaCost key={j} cost={part} size="sm" />
            ) : (
              part
            ),
          )}
        </Text>
      ))}
    </Stack>
  );
}

function CardDetailBody({
  name,
  options,
  onClose,
}: {
  name: string;
  options: OpenOptions;
  onClose: () => void;
}) {
  const { data: card, error, isLoading } = useCard(name);
  const [back, setBack] = useState(false);
  const navigate = useNavigate();
  if (isLoading) return <Loader m="xl" />;
  if (error) return <ErrorAlert error={error} />;
  if (!card) return null;
  const faces = card.faces.length > 0 ? card.faces : [card];
  const buildHref = `/build?${new URLSearchParams({
    commander: card.name,
    ...(options.collection ? { collection: options.collection } : {}),
  })}`;
  return (
    <Grid gap="lg">
      <Grid.Col span={{ base: 12, sm: 5 }}>
        <Stack gap="xs" maw={340} mx="auto">
          <CardImage name={card.name} images={card.images} back={back} />
          {card.images.back && (
            <Button
              variant="light"
              leftSection={<IconRefresh size={16} />}
              onClick={() => setBack((b) => !b)}
            >
              {back ? "Show front" : "Show back"}
            </Button>
          )}
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, sm: 7 }}>
        <Stack gap="sm">
          {faces.map((face) => (
            <Stack key={face.name} gap={4}>
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Title order={3} fz="lg">
                  {face.name}
                </Title>
                <ManaCost cost={face.mana_cost} />
              </Group>
              <Text size="sm" c="dimmed">
                {face.type_line}
                {face.power != null &&
                  face.toughness != null &&
                  ` · ${face.power}/${face.toughness}`}
              </Text>
              <OracleText text={face.oracle_text} />
            </Stack>
          ))}
          <Group gap="xs">
            <RoleBadge role={card.role} />
            {card.is_commander && <Badge variant="light">Commander</Badge>}
            {card.game_changer && (
              <Tooltip label="Limited in power brackets 1–3">
                <Badge color="yellow" variant="light">
                  Game changer
                </Badge>
              </Tooltip>
            )}
            {card.partner_tags.map((t) => (
              <Badge key={t} color="grape" variant="light">
                {t}
              </Badge>
            ))}
          </Group>
          <Grid gap={4}>
            {[
              ["Price", card.price_usd === null ? "no price data" : formatPrice(card.price_usd)],
              ["EDHREC rank", card.edhrec_rank ? `#${card.edhrec_rank}` : "—"],
              ["Rarity", card.rarity || "—"],
              ["Set", card.set_name ? `${card.set_name} (${card.set_code.toUpperCase()})` : "—"],
              ...(options.quantity !== undefined ? [["Owned", `${options.quantity}`]] : []),
            ].map(([k, v]) => (
              <Grid.Col span={6} key={k}>
                <Text size="xs" c="dimmed">
                  {k}
                </Text>
                <Text size="sm">{v}</Text>
              </Grid.Col>
            ))}
          </Grid>
          {card.is_commander && (
            <Button
              leftSection={<IconHammer size={16} />}
              onClick={() => {
                onClose();
                navigate(buildHref);
              }}
            >
              Build with this commander
            </Button>
          )}
        </Stack>
      </Grid.Col>
    </Grid>
  );
}

/** One card-detail modal for the whole app: `useCardDetail()(name)` opens it. */
export function CardDetailProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ name: string; options: OpenOptions } | null>(null);
  const mobile = useMediaQuery("(max-width: 48em)");
  const open = useCallback(
    (name: string, options: OpenOptions = {}) => setState({ name, options }),
    [],
  );
  const close = useCallback(() => setState(null), []);
  const value = useMemo(() => open, [open]);
  return (
    <Context.Provider value={value}>
      {children}
      <Modal
        opened={state !== null}
        onClose={close}
        size="xl"
        fullScreen={mobile}
        title="Card details"
        aria-label={state ? `Card details: ${state.name}` : undefined}
      >
        {state && <CardDetailBody name={state.name} options={state.options} onClose={close} />}
      </Modal>
    </Context.Provider>
  );
}
