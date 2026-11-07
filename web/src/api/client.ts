// Typed API client. Paths and shapes come from schema.gen.ts, generated from the
// FastAPI OpenAPI schema (`npm run gen:api`) — never edit the generated file.
import createClient from "openapi-fetch";
import type { paths } from "./schema.gen";

export const api = createClient<paths>({ baseUrl: "" });

/** Every API failure: {error: {code, message, details, data}} (see docs/UI_PLAN.md §2). */
export interface ApiErrorBody {
  code: string;
  message: string;
  details: string[];
  data: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiErrorBody,
  ) {
    super(body.message);
    this.name = "ApiError";
  }

  get code(): string {
    return this.body.code;
  }
}

function isErrorEnvelope(value: unknown): value is { error: ApiErrorBody } {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as { error: { code?: unknown } }).error?.code === "string"
  );
}

/** Resolve an openapi-fetch call to its data, or throw an ApiError. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: Awaited<typeof call>;
  try {
    result = await call;
  } catch (cause) {
    throw new ApiError(0, {
      code: "network_error",
      message: "The CommanderAI server can't be reached. Is `commanderai serve` running?",
      details: [String(cause)],
      data: {},
    });
  }
  const { data, error, response } = result;
  if (response.ok && error === undefined) return data as T;
  if (isErrorEnvelope(error)) throw new ApiError(response.status, error.error);
  throw new ApiError(response.status, {
    code: "http_error",
    message: `Request failed (${response.status} ${response.statusText})`,
    details: [],
    data: {},
  });
}
