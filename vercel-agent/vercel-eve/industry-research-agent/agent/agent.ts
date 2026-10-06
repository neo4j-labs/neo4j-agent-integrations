import { defineAgent } from "eve";
import { baseModel, MODEL_ID, MODEL_ROUTING } from "./lib/model";

export default defineAgent({
  // Gateway takes a model name; direct OpenAI needs a model object.
  model: MODEL_ROUTING === "openai" ? baseModel() : MODEL_ID,

  reasoning: "medium",
});
