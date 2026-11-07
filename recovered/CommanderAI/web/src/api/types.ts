// Friendly names for the generated API types.
import type { components } from "./schema.gen";

type Schemas = components["schemas"];

export type Status = Schemas["StatusResponse"];
export type Vocabulary = Schemas["Vocabulary"];
export type CardImages = Schemas["CardImages"];
export type CardSummary = Schemas["CardSummary"];
export type CardDetail = Schemas["CardDetail"];
export type CollectionInfo = Schemas["CollectionInfo"];
export type CollectionDetail = Schemas["CollectionDetail"];
export type CollectionCard = Schemas["CollectionCard"];
export type CollectionPreview = Schemas["CollectionPreview"];
export type MatchReport = Schemas["MatchReport"];
export type CommanderEntry = Schemas["CommanderEntry"];
export type CommanderSuggestions = Schemas["CommanderSuggestions"];
/** Build parameters as sent (omitted fields take server defaults). */
export type BuildParams = Schemas["BuildParams-Input"];
/** Build parameters as returned (every field present, seed resolved). */
export type ResolvedBuildParams = Schemas["BuildParams-Output"];
export type BuildResponse = Schemas["BuildResponse"];
export type BuildResult = Schemas["BuildResultDTO"];
export type BuildReport = Schemas["BuildReport"];
export type DeckView = Schemas["DeckView"];
export type DeckCard = Schemas["DeckCard"];
export type DeckStats = Schemas["DeckStats"];
export type DeckSummary = Schemas["DeckSummaryDTO"];
export type DeckList = Schemas["DeckList"];
export type DeckDetail = Schemas["DeckDetail"];
export type Notice = Schemas["Notice"];
export type Token = Schemas["Token"];
export type DeckSlot = Schemas["DeckSlot"];
