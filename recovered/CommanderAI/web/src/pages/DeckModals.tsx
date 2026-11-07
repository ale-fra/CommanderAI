import { Button, FileButton, Group, Modal, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFileUpload } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useDeleteDeck, useImportDeck, useUpdateDeck } from "../api/queries";
import { ErrorAlert } from "../components/Feedback";

export function ImportDeckModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const [content, setContent] = useState("");
  const [filename, setFilename] = useState<string | null>(null);
  const [name, setName] = useState("");
  const importDeck = useImportDeck();
  const navigate = useNavigate();
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset the form only when the modal opens
  useEffect(() => {
    if (opened) {
      setContent("");
      setFilename(null);
      setName("");
      importDeck.reset();
    }
  }, [opened]);
  return (
    <Modal opened={opened} onClose={onClose} size="lg" title="Import a deck">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const result = await importDeck.mutateAsync({
            content,
            name: name.trim() || null,
            filename,
          });
          const unknown = result.unknown_cards.length;
          notifications.show({
            color: unknown ? "yellow" : "teal",
            message: unknown
              ? `Imported "${result.deck.name}" — ${unknown} unknown card(s) skipped: ${result.unknown_cards.join(", ")}`
              : `Imported "${result.deck.name}"`,
            autoClose: unknown ? 10_000 : 4_000,
          });
          onClose();
          navigate(`/decks/${result.deck.id}`);
        }}
      >
        <Stack>
          <Text size="sm" c="dimmed">
            A CommanderAI JSON export, or a decklist in any common format (Moxfield, Archidekt,
            MTGO, plain "1 Card" lines). The commander is the marked card or the first line.
          </Text>
          <Textarea
            label="Deck"
            autosize
            minRows={8}
            maxRows={16}
            value={content}
            onChange={(e) => setContent(e.currentTarget.value)}
            styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }}
          />
          <Group justify="space-between" align="flex-end">
            <FileButton
              accept=".txt,.json,.dec,text/plain,application/json"
              onChange={async (file) => {
                if (!file) return;
                setContent(await file.text());
                setFilename(file.name);
              }}
            >
              {(props) => (
                <Button variant="default" leftSection={<IconFileUpload size={16} />} {...props}>
                  Load a file
                </Button>
              )}
            </FileButton>
            <TextInput
              label="Name (optional)"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              maxLength={200}
              style={{ flex: 1 }}
            />
          </Group>
          {filename && (
            <Text size="xs" c="dimmed">
              File: {filename}
            </Text>
          )}
          {importDeck.error && <ErrorAlert error={importDeck.error} />}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!content.trim()} loading={importDeck.isPending}>
              Import
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

export function RenameDeckModal({
  deck,
  onClose,
}: {
  deck: { id: number; name: string } | null;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const update = useUpdateDeck();
  useEffect(() => {
    if (deck) setName(deck.name);
  }, [deck]);
  return (
    <Modal opened={deck !== null} onClose={onClose} title="Rename deck">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!deck) return;
          await update.mutateAsync({ id: deck.id, name: name.trim() });
          onClose();
        }}
      >
        <Stack>
          <TextInput
            label="Name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            required
            data-autofocus
            maxLength={200}
          />
          {update.error && <ErrorAlert error={update.error} />}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim()} loading={update.isPending}>
              Rename
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

export function DeleteDeckModal({
  deck,
  onClose,
  onDeleted,
}: {
  deck: { id: number; name: string } | null;
  onClose: () => void;
  onDeleted?: () => void;
}) {
  const remove = useDeleteDeck();
  return (
    <Modal opened={deck !== null} onClose={onClose} title="Delete deck">
      <Stack>
        <Text>
          Delete <b>{deck?.name}</b> from the library? Exported files on disk are kept.
        </Text>
        {remove.error && <ErrorAlert error={remove.error} />}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button
            color="red"
            loading={remove.isPending}
            onClick={async () => {
              if (!deck) return;
              await remove.mutateAsync(deck.id);
              notifications.show({ message: `Deleted "${deck.name}"` });
              onClose();
              onDeleted?.();
            }}
          >
            Delete
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
