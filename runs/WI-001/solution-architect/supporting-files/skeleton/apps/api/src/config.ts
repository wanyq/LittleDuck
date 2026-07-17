export interface AppConfig {
  host: string;
  port: number;
  logLevel: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const port = Number(env.PORT ?? "3000");

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("PORT must be an integer between 1 and 65535");
  }

  return {
    host: env.HOST ?? "127.0.0.1",
    port,
    logLevel: env.LOG_LEVEL ?? "info"
  };
}
