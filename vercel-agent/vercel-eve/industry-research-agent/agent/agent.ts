import { defineAgent } from "eve";
import { baseModel, MODEL_ID, MODEL_ROUTING } from "./lib/model";

export default defineAgent({
  model: MODEL_ROUTING === "openai" ? baseModel() : MODEL_ID,
  reasoning: "medium",
  defaultTools: false,
});
