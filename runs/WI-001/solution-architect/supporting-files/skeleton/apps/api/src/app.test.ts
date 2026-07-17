import assert from "node:assert/strict";
import test from "node:test";
import { buildApp } from "./app.js";

test("GET /healthz exposes the WI-001 skeleton health response", async () => {
  const app = buildApp();
  const response = await app.inject({ method: "GET", url: "/healthz" });

  assert.equal(response.statusCode, 200);
  assert.equal(response.json().status, "ok");
  assert.equal(response.json().database, "not_checked");

  await app.close();
});
