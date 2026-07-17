-- LittleDuck MVP PostgreSQL 16+ reference schema.
-- This is an architectural baseline for WI-003, not a production migration.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE conversation_title_status AS ENUM ('temporary', 'final');
CREATE TYPE message_role AS ENUM ('user', 'assistant');
CREATE TYPE message_status AS ENUM (
  'persisted',
  'generating',
  'completed',
  'failed',
  'stopped'
);
CREATE TYPE generation_kind AS ENUM ('chat', 'retry');
CREATE TYPE generation_status AS ENUM (
  'queued',
  'streaming',
  'completed',
  'failed',
  'stopped'
);
CREATE TYPE llm_call_type AS ENUM ('chat', 'title', 'retry');
CREATE TYPE llm_call_status AS ENUM (
  'in_progress',
  'succeeded',
  'failed',
  'stopped'
);
CREATE TYPE job_type AS ENUM ('title_generation');
CREATE TYPE job_status AS ENUM ('pending', 'running', 'succeeded', 'failed');

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone varchar(11) NOT NULL UNIQUE
    CHECK (phone ~ '^1[3-9][0-9]{9}$'),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
  csrf_token_hash bytea NOT NULL CHECK (octet_length(csrf_token_hash) = 32),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  CHECK (expires_at > created_at)
);

CREATE INDEX user_sessions_active_lookup_idx
  ON user_sessions (token_hash, expires_at)
  WHERE revoked_at IS NULL;

CREATE TABLE admins (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username varchar(64) NOT NULL UNIQUE,
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_id uuid NOT NULL REFERENCES admins(id) ON DELETE RESTRICT,
  token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
  csrf_token_hash bytea NOT NULL CHECK (octet_length(csrf_token_hash) = 32),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  CHECK (expires_at > created_at)
);

CREATE INDEX admin_sessions_active_lookup_idx
  ON admin_sessions (token_hash, expires_at)
  WHERE revoked_at IS NULL;

CREATE TABLE conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  title varchar(20) NOT NULL,
  title_status conversation_title_status NOT NULL DEFAULT 'temporary',
  first_user_message_id uuid,
  first_successful_assistant_message_id uuid,
  last_activity_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX conversations_user_activity_idx
  ON conversations (user_id, last_activity_at DESC, id DESC);

CREATE INDEX conversations_user_title_idx
  ON conversations (user_id, title);

CREATE TABLE messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
  author_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  role message_role NOT NULL,
  status message_status NOT NULL,
  content text NOT NULL DEFAULT '',
  client_message_id uuid,
  reply_to_message_id uuid REFERENCES messages(id) ON DELETE RESTRICT,
  retry_of_message_id uuid REFERENCES messages(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (conversation_id, id),
  CHECK (
    (role = 'user'
      AND author_user_id IS NOT NULL
      AND client_message_id IS NOT NULL
      AND status = 'persisted'
      AND reply_to_message_id IS NULL
      AND retry_of_message_id IS NULL)
    OR
    (role = 'assistant'
      AND author_user_id IS NULL
      AND client_message_id IS NULL
      AND status IN ('generating', 'completed', 'failed', 'stopped')
      AND reply_to_message_id IS NOT NULL)
  ),
  CHECK (char_length(content) <= 4000 OR role = 'assistant')
);

CREATE UNIQUE INDEX messages_user_client_id_uq
  ON messages (author_user_id, client_message_id)
  WHERE role = 'user';

CREATE INDEX messages_conversation_chronology_idx
  ON messages (conversation_id, created_at, id);

ALTER TABLE conversations
  ADD CONSTRAINT conversations_first_user_message_fk
  FOREIGN KEY (id, first_user_message_id)
  REFERENCES messages(conversation_id, id) ON DELETE RESTRICT;

ALTER TABLE conversations
  ADD CONSTRAINT conversations_first_successful_assistant_fk
  FOREIGN KEY (id, first_successful_assistant_message_id)
  REFERENCES messages(conversation_id, id) ON DELETE RESTRICT;

CREATE TABLE generations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
  user_message_id uuid NOT NULL REFERENCES messages(id) ON DELETE RESTRICT,
  assistant_message_id uuid NOT NULL UNIQUE REFERENCES messages(id) ON DELETE RESTRICT,
  origin_user_session_id uuid NOT NULL
    REFERENCES user_sessions(id) ON DELETE RESTRICT,
  kind generation_kind NOT NULL,
  status generation_status NOT NULL DEFAULT 'queued',
  idempotency_key_hash bytea NOT NULL
    CHECK (octet_length(idempotency_key_hash) = 32),
  request_fingerprint bytea NOT NULL
    CHECK (octet_length(request_fingerprint) = 32),
  last_event_sequence bigint NOT NULL DEFAULT 0 CHECK (last_event_sequence >= 0),
  cancel_requested_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (conversation_id, id),
  CHECK (
    (status IN ('queued', 'streaming') AND finished_at IS NULL)
    OR
    (status IN ('completed', 'failed', 'stopped') AND finished_at IS NOT NULL)
  )
);

CREATE UNIQUE INDEX generations_session_idempotency_uq
  ON generations (origin_user_session_id, idempotency_key_hash);

ALTER TABLE generations
  ADD CONSTRAINT generations_user_message_same_conversation_fk
  FOREIGN KEY (conversation_id, user_message_id)
  REFERENCES messages(conversation_id, id) ON DELETE RESTRICT;

ALTER TABLE generations
  ADD CONSTRAINT generations_assistant_message_same_conversation_fk
  FOREIGN KEY (conversation_id, assistant_message_id)
  REFERENCES messages(conversation_id, id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX generations_one_active_per_conversation_uq
  ON generations (conversation_id)
  WHERE status IN ('queued', 'streaming');

CREATE INDEX generations_conversation_created_idx
  ON generations (conversation_id, created_at DESC);

ALTER TABLE messages
  ADD COLUMN generation_id uuid REFERENCES generations(id) ON DELETE RESTRICT;

ALTER TABLE messages
  ADD CONSTRAINT messages_generation_same_conversation_fk
  FOREIGN KEY (conversation_id, generation_id)
  REFERENCES generations(conversation_id, id) ON DELETE RESTRICT;

ALTER TABLE messages
  ADD CONSTRAINT messages_reply_same_conversation_fk
  FOREIGN KEY (conversation_id, reply_to_message_id)
  REFERENCES messages(conversation_id, id) ON DELETE RESTRICT;

ALTER TABLE messages
  ADD CONSTRAINT messages_retry_same_conversation_fk
  FOREIGN KEY (conversation_id, retry_of_message_id)
  REFERENCES messages(conversation_id, id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX messages_generation_uq
  ON messages (generation_id)
  WHERE generation_id IS NOT NULL;

CREATE TABLE generation_events (
  generation_id uuid NOT NULL REFERENCES generations(id) ON DELETE RESTRICT,
  sequence bigint NOT NULL CHECK (sequence > 0),
  event_type text NOT NULL CHECK (
    event_type IN (
      'generation.started',
      'generation.delta',
      'generation.completed',
      'generation.failed',
      'generation.stopped'
    )
  ),
  payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (generation_id, sequence)
);

CREATE INDEX generation_events_created_idx
  ON generation_events (created_at);

CREATE TABLE llm_configs (
  id smallint PRIMARY KEY CHECK (id = 1),
  provider text NOT NULL DEFAULT 'openai' CHECK (provider = 'openai'),
  model text NOT NULL CHECK (btrim(model) <> ''),
  api_key_ciphertext bytea NOT NULL,
  api_key_iv bytea NOT NULL CHECK (octet_length(api_key_iv) = 12),
  api_key_tag bytea NOT NULL CHECK (octet_length(api_key_tag) = 16),
  updated_by_admin_id uuid NOT NULL REFERENCES admins(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE llm_calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
  generation_id uuid REFERENCES generations(id) ON DELETE RESTRICT,
  call_type llm_call_type NOT NULL,
  provider text NOT NULL CHECK (provider = 'openai'),
  model text NOT NULL CHECK (btrim(model) <> ''),
  prompt_json jsonb NOT NULL CHECK (jsonb_typeof(prompt_json) = 'array'),
  response_text text NOT NULL DEFAULT '',
  status llm_call_status NOT NULL DEFAULT 'in_progress',
  provider_response_id text,
  provider_error_code text,
  provider_error_message text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (
    (status = 'in_progress' AND finished_at IS NULL)
    OR
    (status IN ('succeeded', 'failed', 'stopped') AND finished_at IS NOT NULL)
  ),
  CHECK (
    (call_type IN ('chat', 'retry') AND generation_id IS NOT NULL)
    OR
    (call_type = 'title')
  )
);

CREATE INDEX llm_calls_topic_chronology_idx
  ON llm_calls (conversation_id, started_at, id);

CREATE INDEX llm_calls_generation_idx
  ON llm_calls (generation_id)
  WHERE generation_id IS NOT NULL;

CREATE TABLE jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type job_type NOT NULL,
  status job_status NOT NULL DEFAULT 'pending',
  dedupe_key text NOT NULL UNIQUE,
  payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  available_at timestamptz NOT NULL DEFAULT now(),
  locked_at timestamptz,
  locked_by text,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX jobs_ready_idx
  ON jobs (available_at, created_at)
  WHERE status = 'pending';

-- Recommended initialization behavior:
-- 1. Hash the literal PRD bootstrap password "admin" with Argon2id in the
--    application initialization command.
-- 2. Insert username "admin" and that hash.
-- 3. Never place the plaintext password in SQL migrations or logs.
