import Fastify, { type FastifyInstance } from "fastify";

export function buildApp(): FastifyInstance {
  const app = Fastify({
    logger: false,
    requestIdHeader: "x-request-id"
  });

  app.get("/healthz", async () => ({
    status: "ok",
    database: "not_checked",
    time: new Date().toISOString()
  }));

  return app;
}
