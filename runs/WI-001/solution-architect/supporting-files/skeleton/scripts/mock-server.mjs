import { createServer } from "node:http";

const host = process.env.MOCK_HOST ?? "127.0.0.1";
const port = Number(process.env.MOCK_PORT ?? "4010");
const now = "2026-07-16T12:00:00Z";

const ids = {
  user: "8c3359aa-49a8-4493-ad2d-302a9b36a59d",
  admin: "bc4cf614-664a-46bf-98e5-b3bc45322fe0",
  conversation: "6bf22123-6db0-4232-929d-3c77272a6ad2",
  userMessage: "d5026980-61a4-4478-a045-bd2efbf17abc",
  assistantMessage: "4cbe9c70-74ff-4d5c-a70f-131722b21589",
  generation: "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
  llmCall: "f8db5c23-360e-420c-bd4d-438e11c29351"
};

const conversation = {
  id: ids.conversation,
  title: "Python脚本求助",
  titleStatus: "final",
  createdAt: now,
  lastActivityAt: "2026-07-16T12:00:04Z",
  messageCount: 2
};

const userMessage = {
  id: ids.userMessage,
  conversationId: ids.conversation,
  sequence: 1,
  role: "user",
  status: "persisted",
  content: "帮我写一个 Python 脚本",
  createdAt: now,
  updatedAt: now
};

const assistantMessage = {
  id: ids.assistantMessage,
  conversationId: ids.conversation,
  sequence: 2,
  role: "assistant",
  status: "completed",
  content: "当然可以。请告诉我脚本要完成什么功能？",
  replyToMessageId: ids.userMessage,
  generationId: ids.generation,
  canRetry: false,
  createdAt: now,
  updatedAt: "2026-07-16T12:00:04Z"
};

const generation = {
  id: ids.generation,
  conversationId: ids.conversation,
  userMessageId: ids.userMessage,
  assistantMessageId: ids.assistantMessage,
  kind: "chat",
  status: "completed",
  stopRequested: false,
  errorCode: null,
  startedAt: now,
  finishedAt: "2026-07-16T12:00:04Z",
  createdAt: now,
  updatedAt: "2026-07-16T12:00:04Z"
};

function json(response, status, body, headers = {}) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    ...headers
  });
  response.end(JSON.stringify(body));
}

function error(response, status, code, message, extra = {}) {
  json(response, status, {
    error: { code, message, requestId: "mock_req_01", ...extra }
  });
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  if (chunks.length === 0) {
    return {};
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function writeEvent(response, event, data) {
  response.write(`event: ${event}\n`);
  response.write(`data: ${JSON.stringify(data)}\n\n`);
}

function streamGeneration(request, response, kind = "chat") {
  const scenario = request.headers["x-mock-scenario"] ?? "chat-success";
  const delay = scenario === "chat-slow" ? 1000 : 80;
  const events = [
    {
      type: "generation.started",
      sequence: 1,
      data: {
        generationId: ids.generation,
        sequence: 1,
        kind,
        conversationId: ids.conversation,
        userMessageId: ids.userMessage,
        assistantMessageId: ids.assistantMessage,
        temporaryTitle: "帮我写一个 Python 脚本",
        occurredAt: now
      }
    },
    {
      type: "generation.delta",
      sequence: 2,
      data: {
        generationId: ids.generation,
        sequence: 2,
        assistantMessageId: ids.assistantMessage,
        delta: "当然可以。",
        accumulatedLength: 6,
        occurredAt: "2026-07-16T12:00:01Z"
      }
    }
  ];

  if (scenario === "chat-failure") {
    events.push({
      type: "generation.failed",
      sequence: 3,
      data: {
        generationId: ids.generation,
        sequence: 3,
        generation: { ...generation, status: "failed", errorCode: "LLM_UNAVAILABLE" },
        assistantMessage: {
          ...assistantMessage,
          status: "failed",
          content: "当然可以。",
          canRetry: true
        },
        error: {
          code: "LLM_UNAVAILABLE",
          message: "回复生成失败，请稍后重试",
          retryable: true
        },
        occurredAt: "2026-07-16T12:00:04Z"
      }
    });
  } else if (scenario === "chat-stopped") {
    events.push({
      type: "generation.stopped",
      sequence: 3,
      data: {
        generationId: ids.generation,
        sequence: 3,
        generation: { ...generation, status: "stopped", stopRequested: true },
        assistantMessage: {
          ...assistantMessage,
          status: "stopped",
          content: "当然可以。",
          canRetry: true
        },
        stoppedBy: "user",
        occurredAt: "2026-07-16T12:00:04Z"
      }
    });
  } else {
    events.push(
      {
        type: "generation.delta",
        sequence: 3,
        data: {
          generationId: ids.generation,
          sequence: 3,
          assistantMessageId: ids.assistantMessage,
          delta: "请告诉我脚本要完成什么功能？",
          accumulatedLength: 21,
          occurredAt: "2026-07-16T12:00:03Z"
        }
      },
      {
        type: "generation.completed",
        sequence: 4,
        data: {
          generationId: ids.generation,
          sequence: 4,
          generation,
          assistantMessage,
          titleWillBeAttempted: true,
          occurredAt: "2026-07-16T12:00:04Z"
        }
      }
    );
  }

  response.writeHead(200, {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    connection: "keep-alive",
    "x-accel-buffering": "no"
  });

  let index = 0;
  const timer = setInterval(() => {
    const event = events[index];
    if (!event) {
      clearInterval(timer);
      response.end();
      return;
    }

    writeEvent(response, event.type, event.data);
    if (scenario === "chat-slow" && event.type === "generation.delta") {
      writeEvent(response, "heartbeat", {
        generationId: ids.generation,
        occurredAt: new Date().toISOString()
      });
    }
    index += 1;
  }, delay);

  request.once("close", () => clearInterval(timer));
}

const server = createServer(async (request, response) => {
  const method = request.method ?? "GET";
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
  const path = url.pathname;

  try {
    if (method === "GET" && path === "/healthz") {
      json(response, 200, { status: "ok", database: "ok", time: new Date().toISOString() });
      return;
    }

    if (method === "POST" && ["/api/v1/user/auth/register", "/api/v1/user/auth/login"].includes(path)) {
      const body = await readJson(request);
      if (body.verificationCode !== "000000") {
        error(response, 400, "INVALID_VERIFICATION_CODE", "验证码错误，请重新输入");
        return;
      }
      json(
        response,
        path.endsWith("register") ? 201 : 200,
        {
          user: { id: ids.user, phone: body.phone ?? "13800138000", createdAt: now },
          expiresAt: "2026-07-23T12:00:00Z"
        },
        { "set-cookie": "ld_user_session=mock; HttpOnly; SameSite=Lax; Path=/api/v1/user" }
      );
      return;
    }

    if (method === "GET" && path === "/api/v1/user/auth/session") {
      json(response, 200, {
        user: { id: ids.user, phone: "13800138000", createdAt: now },
        expiresAt: "2026-07-23T12:00:00Z"
      });
      return;
    }

    if (method === "POST" && path === "/api/v1/user/auth/logout") {
      response.writeHead(204, {
        "set-cookie": "ld_user_session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/api/v1/user"
      });
      response.end();
      return;
    }

    if (method === "GET" && path === "/api/v1/user/conversations") {
      json(response, 200, { items: [conversation], page: 1, pageSize: 20, total: 1 });
      return;
    }

    if (method === "GET" && path === `/api/v1/user/conversations/${ids.conversation}`) {
      json(response, 200, { conversation, canSend: true, activeGeneration: null });
      return;
    }

    if (method === "GET" && path === `/api/v1/user/conversations/${ids.conversation}/messages`) {
      json(response, 200, {
        items: [userMessage, assistantMessage],
        page: 1,
        pageSize: 30,
        total: 2
      });
      return;
    }

    if (method === "POST" && path === "/api/v1/user/generations") {
      const body = await readJson(request);
      if (typeof body.content !== "string" || body.content.trim().length < 1 || body.content.trim().length > 4000) {
        error(response, 400, "VALIDATION_ERROR", "请求参数不正确");
        return;
      }
      if (request.headers["x-mock-scenario"] === "duplicate-message") {
        error(response, 409, "DUPLICATE_MESSAGE", "该消息已经提交，请读取已有生成状态", {
          generationId: ids.generation
        });
        return;
      }
      streamGeneration(request, response, "chat");
      return;
    }

    if (method === "GET" && path === `/api/v1/user/generations/${ids.generation}`) {
      json(response, 200, { generation, assistantMessage });
      return;
    }

    if (method === "POST" && path === `/api/v1/user/generations/${ids.generation}/stop`) {
      json(response, 202, {
        generation: {
          ...generation,
          status: "streaming",
          errorCode: null,
          finishedAt: null,
          stopRequested: true,
          updatedAt: new Date().toISOString()
        },
        assistantMessage: {
          ...assistantMessage,
          status: "generating",
          content: "当然可以。",
          canRetry: false
        }
      });
      return;
    }

    if (method === "POST" && path.endsWith("/retries")) {
      streamGeneration(request, response, "retry");
      return;
    }

    if (method === "POST" && path === "/api/v1/admin/auth/login") {
      const body = await readJson(request);
      if (body.username !== "admin" || body.password !== "admin") {
        error(response, 401, "INVALID_CREDENTIALS", "账号或密码错误");
        return;
      }
      json(
        response,
        200,
        {
          admin: { id: ids.admin, username: "admin" },
          expiresAt: "2026-07-17T00:00:00Z"
        },
        { "set-cookie": "ld_admin_session=mock; HttpOnly; SameSite=Lax; Path=/api/v1/admin" }
      );
      return;
    }

    if (method === "GET" && path === "/api/v1/admin/auth/session") {
      json(response, 200, {
        admin: { id: ids.admin, username: "admin" },
        expiresAt: "2026-07-17T00:00:00Z"
      });
      return;
    }

    if (method === "POST" && path === "/api/v1/admin/auth/logout") {
      response.writeHead(204);
      response.end();
      return;
    }

    if (method === "GET" && path === "/api/v1/admin/llm-config") {
      json(response, 200, {
        configured: true,
        config: {
          provider: "openai",
          apiKey: "<mock-plaintext-visible-to-admin>",
          model: "example-model",
          updatedAt: now
        }
      });
      return;
    }

    if (method === "PUT" && path === "/api/v1/admin/llm-config") {
      const body = await readJson(request);
      json(response, 200, { configured: true, config: { ...body, updatedAt: now } });
      return;
    }

    if (method === "POST" && path === "/api/v1/admin/llm-config/test") {
      const body = await readJson(request);
      const success = request.headers["x-mock-scenario"] !== "config-test-failure";
      json(response, 200, {
        success,
        provider: "openai",
        model: body.model ?? "example-model",
        ...(success
          ? {}
          : { providerError: { code: "invalid_api_key", message: "Mock invalid API key" } }),
        testedAt: now
      });
      return;
    }

    if (method === "GET" && path === "/api/v1/admin/topics") {
      json(response, 200, {
        items: [{
          id: ids.conversation,
          title: conversation.title,
          phone: "13800138000",
          messageCount: 2,
          llmCallCount: 1,
          createdAt: now,
          lastActivityAt: conversation.lastActivityAt
        }],
        page: 1,
        pageSize: 20,
        total: 1
      });
      return;
    }

    if (method === "GET" && path === `/api/v1/admin/topics/${ids.conversation}`) {
      json(response, 200, {
        topic: {
          id: ids.conversation,
          title: conversation.title,
          phone: "13800138000",
          messageCount: 2,
          llmCallCount: 1,
          createdAt: now,
          lastActivityAt: conversation.lastActivityAt
        }
      });
      return;
    }

    if (method === "GET" && path === `/api/v1/admin/topics/${ids.conversation}/messages`) {
      json(response, 200, {
        items: [userMessage, assistantMessage],
        page: 1,
        pageSize: 50,
        total: 2
      });
      return;
    }

    if (method === "GET" && path === `/api/v1/admin/topics/${ids.conversation}/llm-calls`) {
      json(response, 200, {
        items: [{
          id: ids.llmCall,
          step: 1,
          callType: "chat",
          relatedMessageId: ids.assistantMessage,
          provider: "openai",
          model: "example-model",
          prompt: [{ role: "user", content: userMessage.content }],
          responseText: assistantMessage.content,
          status: "succeeded",
          providerResponseId: "resp_mock",
          providerError: null,
          startedAt: now,
          finishedAt: "2026-07-16T12:00:04Z"
        }],
        page: 1,
        pageSize: 50,
        total: 1
      });
      return;
    }

    error(response, 404, "RESOURCE_NOT_FOUND", "资源不存在");
  } catch (cause) {
    console.error(cause);
    error(response, 500, "INTERNAL_ERROR", "服务暂时不可用");
  }
});

server.listen(port, host, () => {
  console.log(`LittleDuck contract mock listening on http://${host}:${port}`);
});

const shutdown = () => server.close(() => process.exit(0));
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
