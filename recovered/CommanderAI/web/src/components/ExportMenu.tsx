import { Button, Menu } from "@mantine/core";
import { useClipboard } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconChevronDown, IconCopy, IconDownload } from "@tabler/icons-react";
import { exportUrl, fetchExport } from "../api/queries";
import type { DeckView } from "../api/types";
import { deckToText, TEXT_FORMATS, type TextFormat } from "../lib/exportDeck";

const FILE_FORMATS = [
  { value: "json", label: "CommanderAI JSON (re-importable)" },
  { value: "text", label: "Readable list (by role)" },
  { value: "moxfield", label: "Moxfield" },
  { value: "archidekt", label: "Archidekt" },
  { value: "mtgo", label: "MTGO / plain list" },
] as const;

/** Copy/download a deck. Saved decks use the API; previews are exported in the browser. */
export function ExportMenu({ deckId, deck }: { deckId?: number; deck: DeckView }) {
  const clipboard = useClipboard();
  const copy = async (format: TextFormat) => {
    try {
      const text =
        deckId !== undefined ? await fetchExport(deckId, format) : deckToText(deck, format);
      clipboard.copy(text);
      notifications.show({ color: "teal", message: `Copied the ${format} list to the clipboard` });
    } catch (e) {
      notifications.show({ color: "red", title: "Copy failed", message: String(e) });
    }
  };
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <Button variant="default" rightSection={<IconChevronDown size={14} />}>
          Export
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Copy to clipboard</Menu.Label>
        {TEXT_FORMATS.map((f) => (
          <Menu.Item
            key={f.value}
            leftSection={<IconCopy size={14} />}
            onClick={() => copy(f.value)}
          >
            {f.label}
          </Menu.Item>
        ))}
        {deckId !== undefined && (
          <>
            <Menu.Divider />
            <Menu.Label>Download</Menu.Label>
            {FILE_FORMATS.map((f) => (
              <Menu.Item
                key={f.value}
                component="a"
                href={exportUrl(deckId, f.value)}
                download
                leftSection={<IconDownload size={14} />}
              >
                {f.label}
              </Menu.Item>
            ))}
          </>
        )}
      </Menu.Dropdown>
    </Menu>
  );
}
