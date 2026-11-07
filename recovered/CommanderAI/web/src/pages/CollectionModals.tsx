import {
  Alert,
  Badge,
  Button,
  FileButton,
  Group,
  List,
  Modal,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFileUpload } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import {
  useCreateCollection,
  useDeleteCollection,
  usePreviewCollection,
  useUpdateCollection,
} from "../api/queries";
import type { CollectionInfo, CollectionPreview } from "../api/types";
import { ErrorAlert } from "../components/Feedback";
import { useActiveCollection } from "../state/ActiveCollection";

function PreviewSummary({ preview }: { preview: CollectionPreview }) {
  const { match } = preview;
  return (
    <Stack gap="xs" data-testid="upload-preview">
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
        {[
          ["Lines", preview.entries],
          ["Copies", preview.copies],
          ["Unique cards", preview.unique_cards],
          ["Commanders", preview.commanders],
        ].map(([label, value]) => (
          <div key={label}>
            <Text size="xs" c="dimmed">
              {label}
            </Text>
            <Text fw={700}>{value}</Text>
          </div>
        ))}
      </SimpleGrid>
      {match.fuzzy.length > 0 && (
        <Alert color="yellow" variant="light" title={`${match.fuzzy.length} name(s) corrected`}>
          <List size="xs">
            {match.fuzzy.map((f) => (
              <List.Item key={f.original}>
                {f.original} → {f.corrected}
              </List.Item>
            ))}
          </List>
        </Alert>
      )}
      {match.unmatched.length > 0 && (
        <Alert
          color="red"
          variant="light"
          title={`${match.unmatched.length} card(s) not found (ignored)`}
        >
          <Text size="xs">{match.unmatched.join(", ")}</Text>
        </Alert>
      )}
      {match.skipped.length > 0 && (
        <Text size="xs" c="dimmed">
          Skipped tokens / special cards: {match.skipped.join(", ")}
        </Text>
      )}
    </Stack>
  );
}

/** Upload a new collection, or replace the content of a stored one. */
export function UploadCollectionModal({
  opened,
  onClose,
  replace,
}: {
  opened: boolean;
  onClose: () => void;
  replace?: CollectionInfo | null;
}) {
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const preview = usePreviewCollection();
  const create = useCreateCollection();
  const update = useUpdateCollection();
  const { setId } = useActiveCollection();

  // biome-ignore lint/correctness/useExhaustiveDependencies: reset the form only when the modal opens
  useEffect(() => {
    if (opened) {
      setName("");
      setContent("");
      preview.reset();
      create.reset();
      update.reset();
    }
  }, [opened]);

  const readFile = async (file: File | null) => {
    if (!file) return;
    setContent(await file.text());
    if (!name && !replace) setName(file.name.replace(/\.(txt|csv)$/i, ""));
    preview.reset();
  };

  const save = async () => {
    if (replace) {
      await update.mutateAsync({ id: replace.id, content });
      notifications.show({ color: "teal", message: `Replaced the cards of "${replace.name}"` });
    } else {
      const created = await create.mutateAsync({ name: name.trim(), content });
      setId(created.id);
      notifications.show({
        color: "teal",
        message: `Saved "${created.name}" and made it the active collection`,
      });
    }
    onClose();
  };

  const error = preview.error ?? create.error ?? update.error;
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size="lg"
      title={replace ? `Replace the cards of "${replace.name}"` : "Upload a collection"}
    >
      <Stack>
        {!replace && (
          <TextInput
            label="Name"
            required
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            maxLength={100}
          />
        )}
        <Textarea
          label="Cards"
          description='One card per line ("1 Sol Ring", "2x Forest"), or a CSV export from Archidekt / Moxfield.'
          autosize
          minRows={8}
          maxRows={16}
          value={content}
          onChange={(e) => {
            setContent(e.currentTarget.value);
            preview.reset();
          }}
          styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }}
        />
        <Group justify="space-between">
          <FileButton onChange={readFile} accept=".txt,.csv,text/plain,text/csv">
            {(props) => (
              <Button variant="default" leftSection={<IconFileUpload size={16} />} {...props}>
                Load a file
              </Button>
            )}
          </FileButton>
          <Button
            variant="light"
            onClick={() => preview.mutate(content)}
            disabled={!content.trim()}
            loading={preview.isPending}
          >
            Check cards
          </Button>
        </Group>
        {error && <ErrorAlert error={error} />}
        {preview.data && <PreviewSummary preview={preview.data} />}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={save}
            disabled={!preview.data || (!replace && !name.trim())}
            loading={create.isPending || update.isPending}
          >
            {replace ? "Replace cards" : "Save collection"}
          </Button>
        </Group>
        {!preview.data && (
          <Text size="xs" c="dimmed" ta="right">
            Check the cards first to see how they match the catalog.
          </Text>
        )}
      </Stack>
    </Modal>
  );
}

export function RenameCollectionModal({
  collection,
  onClose,
}: {
  collection: CollectionInfo | null;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const update = useUpdateCollection();
  useEffect(() => {
    if (collection) setName(collection.name);
  }, [collection]);
  return (
    <Modal opened={collection !== null} onClose={onClose} title="Rename collection">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!collection) return;
          await update.mutateAsync({ id: collection.id, name: name.trim() });
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

export function DeleteCollectionModal({
  collection,
  onClose,
}: {
  collection: CollectionInfo | null;
  onClose: () => void;
}) {
  const remove = useDeleteCollection();
  return (
    <Modal opened={collection !== null} onClose={onClose} title="Delete collection">
      <Stack>
        <Text>
          Delete <b>{collection?.name}</b>? Decks built from it are kept.{" "}
          <Badge color="red">This can't be undone</Badge>
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
              if (!collection) return;
              await remove.mutateAsync(collection.id);
              notifications.show({ message: `Deleted "${collection.name}"` });
              onClose();
            }}
          >
            Delete
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
