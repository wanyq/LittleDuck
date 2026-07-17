import { readFile, readdir } from "node:fs/promises";
import { extname, resolve } from "node:path";

const root = resolve(process.cwd(), "../..");
const ignoredDirs = new Set(["node_modules", "dist", ".git", ".venv"]);
const ignoredFiles = new Set(["pnpm-lock.yaml", "scan-secrets.mjs"]);
const textExtensions = new Set([
  ".css",
  ".example",
  ".html",
  ".ini",
  ".js",
  ".json",
  ".key",
  ".md",
  ".mjs",
  ".pem",
  ".py",
  ".sql",
  ".toml",
  ".ts",
  ".tsx",
  ".txt",
  ".yaml",
  ".yml"
]);

const highConfidencePatterns = [
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /\bsk-[A-Za-z0-9_-]{20,}\b/,
  /\bgh[oprsu]_[A-Za-z0-9]{30,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /API_KEY_ENCRYPTION_KEY=(?!REPLACE_)[^\s]+/,
  /DATABASE_URL=(?:postgresql|mysql)(?:\+[a-z0-9_]+)?:\/\/[^:\s]+:(?!(?:REPLACE_[^@\s]*|local-only)@)[^@\s]+@/i
];

const findings = [];

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && ignoredDirs.has(entry.name)) {
      continue;
    }
    if (entry.isFile() && ignoredFiles.has(entry.name)) {
      continue;
    }

    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) {
      await walk(path);
      continue;
    }
    if (!textExtensions.has(extname(entry.name)) && !entry.name.startsWith(".env")) {
      continue;
    }

    const text = await readFile(path, "utf8");
    for (const pattern of highConfidencePatterns) {
      if (pattern.test(text)) {
        findings.push(`${path}: ${pattern}`);
      }
    }
  }
}

await walk(root);

if (findings.length > 0) {
  console.error(findings.join("\n"));
  process.exit(1);
}

console.log("OK no high-confidence credential patterns found");
