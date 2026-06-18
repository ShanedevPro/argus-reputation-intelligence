import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { customProvider } from "ai";
import { isTestEnvironment } from "../constants";
import {
  ARGUS_CHAT_PROVIDER_NAME,
  assertArgusChatConfigured,
} from "./argus-chat-config";

function createArgusChatProvider() {
  const config = assertArgusChatConfigured();
  return createOpenAICompatible({
    name: ARGUS_CHAT_PROVIDER_NAME,
    baseURL: config.baseURL,
    apiKey: config.apiKey,
    includeUsage: true,
  });
}

export const myProvider = isTestEnvironment
  ? (() => {
      const { chatModel, titleModel } = require("./models.mock");
      return customProvider({
        languageModels: {
          "chat-model": chatModel,
          "title-model": titleModel,
        },
      });
    })()
  : null;

export function getLanguageModel(modelId: string) {
  if (isTestEnvironment && myProvider) {
    return myProvider.languageModel("chat-model");
  }

  const config = assertArgusChatConfigured();
  return createArgusChatProvider().chatModel(config.model || modelId);
}

export function getTitleModel() {
  if (isTestEnvironment && myProvider) {
    return myProvider.languageModel("title-model");
  }

  const config = assertArgusChatConfigured();
  return createArgusChatProvider().chatModel(config.titleModel);
}
