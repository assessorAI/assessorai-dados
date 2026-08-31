CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS propositions (
    id UUID PRIMARY KEY,
    canonical_key TEXT NOT NULL UNIQUE,
    country CHAR(2) NOT NULL DEFAULT 'BR',
    jurisdiction_level TEXT NOT NULL,
    state CHAR(2),
    municipality TEXT,
    house TEXT NOT NULL,
    type TEXT,
    number TEXT,
    year INTEGER,
    title TEXT NOT NULL,
    subject TEXT,
    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    presentation_date DATE,
    status TEXT,
    full_text TEXT,
    source_url TEXT,
    text_extraction_method TEXT,
    collected_at TIMESTAMPTZ,
    content_hash CHAR(64) NOT NULL,
    provenance JSONB NOT NULL DEFAULT '[]'::jsonb,
    dataset_release TEXT NOT NULL,
    embedding vector(1536),
    search_document tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('portuguese', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('portuguese', coalesce(subject, '')), 'B') ||
        setweight(to_tsvector('portuguese', coalesce(full_text, '')), 'C')
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_propositions_identity
    ON propositions (house, type, number, year);
CREATE INDEX IF NOT EXISTS idx_propositions_filters
    ON propositions (state, municipality, year);
CREATE INDEX IF NOT EXISTS idx_propositions_search
    ON propositions USING GIN (search_document);
CREATE INDEX IF NOT EXISTS idx_propositions_embedding
    ON propositions USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS proposition_sources (
    proposition_id UUID NOT NULL REFERENCES propositions(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    source_record_id TEXT,
    source_url TEXT,
    source_file TEXT NOT NULL,
    scraped_at TIMESTAMPTZ,
    extraction_method TEXT,
    content_hash CHAR(64) NOT NULL,
    redistribution_status TEXT NOT NULL,
    PRIMARY KEY (proposition_id, source_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_proposition_sources_source
    ON proposition_sources (source_id, source_record_id);

CREATE TABLE IF NOT EXISTS proposition_texts (
    proposition_id UUID NOT NULL REFERENCES propositions(id) ON DELETE CASCADE,
    content_hash CHAR(64) NOT NULL,
    chunk_number INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    PRIMARY KEY (proposition_id, content_hash, chunk_number)
);

CREATE TABLE IF NOT EXISTS dataset_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    house TEXT,
    jurisdiction_level TEXT NOT NULL,
    state CHAR(2),
    municipality TEXT,
    terms_url TEXT,
    source_license TEXT,
    redistribution_status TEXT NOT NULL,
    attribution TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dataset_releases (
    version TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    proposition_count INTEGER NOT NULL,
    manifest JSONB NOT NULL,
    github_repository TEXT NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
