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
    if (event === "heartbeat") {
      if (fields.has("id")) {
        throw new Error(`${file}: heartbeat must not have id`);
      }
      continue;
    }

    firstBusinessEvent ??= event;
    const id = Number(fields.get("id"));
    if (id !== expectedSequence || data.sequence !== expectedSequence) {
      throw new Error(
        `${file}: expected sequence ${expectedSequence}, got id=${id} data.sequence=${data.sequence}`
      );
    }
    expectedSequence += 1;

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

  console.log(`OK ${file}: ${expectedSequence - 1} persisted events`);
}
