-- Batchmate memory store on Supabase (Postgres + pgvector). Run once in the SQL editor.
create extension if not exists vector;

create table if not exists memories (
  id            text primary key,
  scope         text not null,          -- student-<id> | company-<name> | batch-<year>
  kind          text not null,          -- weakness | strength | session | experience | pattern | lesson
  text          text not null,
  meta          jsonb not null default '{}',
  source_count  int  not null default 1,
  status        text not null default 'active',  -- active | proposed | rejected | resolved
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  embedding     vector(384) not null
);

create index if not exists memories_scope_idx on memories (scope, kind, status);
create index if not exists memories_embedding_idx on memories
  using hnsw (embedding vector_cosine_ops);

-- Personal scopes are enforced in the app layer (MemoryService.check_access) and the backend
-- uses the service key. Keep RLS on so the anon key can never read memories directly.
alter table memories enable row level security;

create or replace function match_memories(
  query_embedding vector(384),
  match_scopes    text[],
  match_kinds     text[] default null,
  match_statuses  text[] default array['active'],
  match_count     int default 20
) returns table (
  id text, scope text, kind text, text text, meta jsonb, source_count int, status text,
  created_at timestamptz, updated_at timestamptz, similarity float
) language sql stable as $$
  select m.id, m.scope, m.kind, m.text, m.meta, m.source_count, m.status,
         m.created_at, m.updated_at,
         1 - (m.embedding <=> query_embedding) as similarity
  from memories m
  where m.scope = any(match_scopes)
    and m.status = any(match_statuses)
    and (match_kinds is null or m.kind = any(match_kinds))
  order by m.embedding <=> query_embedding
  limit match_count;
$$;
