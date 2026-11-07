import { ApiError } from "../api/client";

export interface FriendlyError {
  title: string;
  message: string;
  details: string[];
}

// Titles for API error codes (messages come from the server, which already
// explains the specific problem).
const TITLES: Record<string, string> = {
  network_error: "Can't reach the server",
  validation_error: "Some values are not valid",
  unknown_theme: "Unknown theme",
  unknown_colors: "Unknown colors",
  invalid_request: "Can't do that",
  card_not_found: "Card not found",
  collection_not_found: "Collection not found",
  deck_not_found: "Deck not found",
  illegal_commander: "Not a legal commander",
  illegal_partner: "These commanders can't be partners",
  empty_collection: "No cards found",
  collection_too_small: "Collection too small",
  insufficient_cards: "Not enough cards",
  no_matching_commander: "No matching commander",
  read_only: "Read-only collection",
  gone: "Preview expired",
  deck_import_failed: "Import failed",
  catalog_not_found: "Card database missing",
};

const HINTS: Record<string, string> = {
  collection_too_small: "Pick a larger collection in the header.",
  insufficient_cards: "Try a commander with more colors, or a larger collection.",
  no_matching_commander: "Widen the colors or choose another theme.",
  gone: "Build again — the same seed produces the same deck — then save it.",
  network_error: "Start it with `commanderai serve`, then retry.",
};

export function friendlyError(error: unknown): FriendlyError {
  if (error instanceof ApiError) {
    const hint = HINTS[error.code];
    return {
      title: TITLES[error.code] ?? "Something went wrong",
      message: hint ? `${error.message} ${hint}` : error.message,
      details: error.body.details,
    };
  }
  return {
    title: "Something went wrong",
    message: error instanceof Error ? error.message : String(error),
    details: [],
  };
}
