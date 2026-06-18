export const ARGUS_CHAT_DEFAULT_MODEL = "mimo/mimo-v2.5-pro";
export const ARGUS_CHAT_PROVIDER_NAME = "argus-chat";
export const ARGUS_CHAT_NOT_CONFIGURED_MESSAGE =
  "Argus chat provider is not configured. Set ARGUS_CHAT_BASE_URL and ARGUS_CHAT_API_KEY, or provide BettaFish engine model environment variables.";

type MissingConfigPiece = "baseURL" | "apiKey";

export type ArgusChatConfig = {
  baseURL?: string;
  apiKey?: string;
  model: string;
  titleModel: string;
  configured: boolean;
  missing: MissingConfigPiece[];
};

export class ArgusChatConfigurationError extends Error {
  missing: MissingConfigPiece[];

  constructor(missing: MissingConfigPiece[]) {
    super(ARGUS_CHAT_NOT_CONFIGURED_MESSAGE);
    this.name = "ArgusChatConfigurationError";
    this.missing = missing;
  }
}

export function getArgusChatConfig(
  env: NodeJS.ProcessEnv = process.env
): ArgusChatConfig {
  const baseURL = firstPresent(
    env.ARGUS_CHAT_BASE_URL,
    env.QUERY_ENGINE_BASE_URL,
    env.REPORT_ENGINE_BASE_URL,
    env.INSIGHT_ENGINE_BASE_URL,
    env.MEDIA_ENGINE_BASE_URL
  );
  const apiKey = firstPresent(
    env.ARGUS_CHAT_API_KEY,
    env.QUERY_ENGINE_API_KEY,
    env.REPORT_ENGINE_API_KEY,
    env.INSIGHT_ENGINE_API_KEY,
    env.MEDIA_ENGINE_API_KEY
  );
  const model =
    firstPresent(env.ARGUS_CHAT_MODEL, env.QUERY_ENGINE_MODEL_NAME) ??
    ARGUS_CHAT_DEFAULT_MODEL;
  const titleModel =
    firstPresent(
      env.ARGUS_CHAT_TITLE_MODEL,
      env.ARGUS_CHAT_MODEL,
      env.QUERY_ENGINE_MODEL_NAME
    ) ?? ARGUS_CHAT_DEFAULT_MODEL;

  const missing: MissingConfigPiece[] = [];
  if (!baseURL) {
    missing.push("baseURL");
  }
  if (!apiKey) {
    missing.push("apiKey");
  }

  return {
    baseURL,
    apiKey,
    model,
    titleModel,
    configured: missing.length === 0,
    missing,
  };
}

export function assertArgusChatConfigured(
  config: ArgusChatConfig = getArgusChatConfig()
) {
  if (!config.configured) {
    throw new ArgusChatConfigurationError(config.missing);
  }

  return config as ArgusChatConfig & {
    baseURL: string;
    apiKey: string;
  };
}

function firstPresent(...values: Array<string | undefined>) {
  for (const value of values) {
    const cleaned = value?.trim();
    if (cleaned) {
      return cleaned;
    }
  }
  return undefined;
}
