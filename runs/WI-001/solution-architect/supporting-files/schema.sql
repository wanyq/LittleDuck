-- LittleDuck MVP PostgreSQL 16 reference schema.
-- The executable migration lives in skeleton/apps/api/migrations/versions/0001_initial.py.

CREATE TABLE users (
  id uuid PRIMARY KEY,
  phone varchar(20) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_sessions (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash varchar(64) NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_user_sessions_user_id ON user_sessions(user_id);

CREATE TABLE admins (
  id uuid PRIMARY KEY,
  username varchar(64) NOT NULL UNIQUE,
  password_hash varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin_sessions (
  id uuid PRIMARY KEY,
  admin_id uuid NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
  token_hash varchar(64) NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE llm_configs (
  id integer PRIMARY KEY CHECK (id = 1),
  provider varchar(32) NOT NULL,
  model varchar(128) NOT NULL,
  api_key_ciphertext bytea NOT NULL,
  api_key_nonce bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE conversations (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title varchar(20) NOT NULL,
  title_status varchar(16) NOT NULL
    CHECK (title_status IN ('temporary', 'final')),
  last_activity_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_conversations_user_activity
  ON conversations(user_id, last_activity_at);

CREATE TABLE messages (
  id uuid PRIMARY KEY,
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role varchar(16) NOT NULL CHECK (role IN ('user', 'assistant')),
  status varchar(16) NOT NULL CHECK (
    status IN ('persisted', 'generating', 'completed', 'failed', 'stopped')
  ),
  content text NOT NULL DEFAULT '',
  reply_to_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
  retry_of_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_messages_conversation_created
  ON messages(conversation_id, created_at);

CREATE TABLE generations (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  user_message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  assistant_message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  client_request_id uuid NOT NULL,
  kind varchar(16) NOT NULL CHECK (kind IN ('chat', 'retry')),
  status varchar(16) NOT NULL CHECK (
    status IN ('streaming', 'completed', 'failed', 'stopped')
  ),
  stop_requested boolean NOT NULL DEFAULT false,
  error_code varchar(64),
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_generation_client_request UNIQUE (user_id, client_request_id)
);
CREATE INDEX ix_generations_conversation_status
  ON generations(conversation_id, status);
CREATE UNIQUE INDEX uq_generations_one_streaming_per_conversation
  ON generations(conversation_id)
  WHERE status = 'streaming';

CREATE TABLE llm_calls (
  id uuid PRIMARY KEY,
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  generation_id uuid REFERENCES generations(id) ON DELETE SET NULL,
  related_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
  call_type varchar(16) NOT NULL CHECK (call_type IN ('chat', 'title', 'retry')),
  provider varchar(32) NOT NULL,
  model varchar(128) NOT NULL,
  prompt jsonb NOT NULL,
  response_text text NOT NULL DEFAULT '',
  status varchar(16) NOT NULL CHECK (
    status IN ('in_progress', 'succeeded', 'failed', 'stopped')
  ),
  provider_response_id varchar(255),
  provider_error jsonb,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  CONSTRAINT uq_llm_call_generation UNIQUE (generation_id)
);
CREATE INDEX ix_llm_calls_conversation_started
  ON llm_calls(conversation_id, started_at);

-- Required ownership query shape. Never query user resources by id alone.
-- SELECT * FROM conversations WHERE id = :conversation_id AND user_id = :current_user_id;
