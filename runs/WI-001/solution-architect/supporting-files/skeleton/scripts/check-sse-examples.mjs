import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";

const examplesDir = resolve(process.cwd(), "../examples");
const files = (await readdir(examplesDir))
  .filter((name) => name.startsWith("sse-") && name.endsWith(".txt"))
  .sort();

if (files.length === 0) {
  throw new Error("no SSE examples found");
}

const terminalEvents = new Set([
  "generation.completed",
  "generation.failed",
  "generation.stopped"
]);

function requireKeys(file, event, data, keys) {
  for (const key of keys) {
    if (!(key in data)) {
      throw new Error(`${file}: ${event} is missing ${key}`);
    }
  }
}

for (const file of files) {
  const source = await readFile(resolve(examplesDir, file), "utf8");
  const frames = source.trim().split(/\n\n+/);
  let expectedSequence = 1;
  let terminalCount = 0;
  let firstBusinessEvent;

  for (const frame of frames) {
    const fields = new Map();
    for (const line of frame.split("\n")) {
      const separator = line.indexOf(":");
      if (separator < 0) {
        throw new Error(`${file}: invalid SSE line ${line}`);
      }
      fields.set(line.slice(0, separator), line.slice(separator + 1).trimStart());
    }

    const event = fields.get("event");
    const dataText = fields.get("data");
    if (!event || !dataText) {
      throw new Error(`${file}: every frame needs event and data`);
    }

    const data = JSON.parse(dataText);
    if (fields.has("id")) {
      throw new Error(`${file}: P0 protocol does not publish replayable SSE id fields`);
    }
    if (event === "heartbeat") {
      if ("sequence" in data) {
        throw new Error(`${file}: heartbeat must not advance the business sequence`);
      }
      if (!String(data.occurredAt ?? "").endsWith("Z")) {
        throw new Error(`${file}: heartbeat occurredAt must be UTC`);
      }
      continue;
    }

    firstBusinessEvent ??= event;
    requireKeys(file, event, data, ["generationId", "sequence", "occurredAt"]);
    if (!String(data.occurredAt).endsWith("Z")) {
      throw new Error(`${file}: ${event} occurredAt must be UTC`);
    }
    if (data.sequence !== expectedSequence) {
      throw new Error(
        `${file}: expected data.sequence=${expectedSequence}, got ${data.sequence}`
      );
    }
    expectedSequence += 1;

    if (event === "generation.started") {
      requireKeys(file, event, data, [
        "kind",
        "conversationId",
        "userMessageId",
        "assistantMessageId",
        "temporaryTitle"
      ]);
    } else if (event === "generation.delta") {
      requireKeys(file, event, data, ["assistantMessageId", "delta", "accumulatedLength"]);
      if (typeof data.delta !== "string" || data.delta.length < 1) {
        throw new Error(`${file}: generation.delta must not be empty`);
      }
    } else if (terminalEvents.has(event)) {
      requireKeys(file, event, data, ["generation", "assistantMessage"]);
      requireKeys(file, event, data.generation, [
        "stopRequested",
        "errorCode",
        "startedAt",
        "finishedAt",
        "createdAt",
        "updatedAt"
      ]);
      requireKeys(file, event, data.assistantMessage, ["sequence"]);
      const expectedStatus = event.slice("generation.".length);
      if (
        data.generation.status !== expectedStatus ||
        data.assistantMessage.status !== expectedStatus
      ) {
        throw new Error(`${file}: ${event} terminal objects do not share ${expectedStatus}`);
      }
      if (event === "generation.failed") {
        requireKeys(file, event, data, ["error"]);
        if (data.generation.errorCode !== data.error.code) {
          throw new Error(`${file}: failed generation errorCode must match event error`);
        }
      } else if (data.generation.errorCode !== null) {
        throw new Error(`${file}: non-failed generation errorCode must be null`);
      }
      if (event === "generation.stopped") {
        requireKeys(file, event, data, ["stoppedBy"]);
      }
      if (event === "generation.completed") {
        requireKeys(file, event, data, ["titleWillBeAttempted"]);
      }
    } else {
      throw new Error(`${file}: unknown business event ${event}`);
    }

    if (terminalEvents.has(event)) {
      terminalCount += 1;
    }
  }

  if (firstBusinessEvent !== "generation.started") {
    throw new Error(`${file}: first business event must be generation.started`);
  }
  if (terminalCount !== 1) {
    throw new Error(`${file}: expected exactly one terminal event`);
  }

  console.log(`OK ${file}: ${expectedSequence - 1} ordered business events`);
}
