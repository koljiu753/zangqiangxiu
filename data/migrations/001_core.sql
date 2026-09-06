BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE record_status AS ENUM ('draft','in_review','approved','rejected','archived');
CREATE TYPE visibility_level AS ENUM ('private','internal_only','public');
CREATE TYPE asset_role AS ENUM ('source','crop','thumbnail','vector','reference','generated');
CREATE TYPE relation_kind AS ENUM ('derived_from','contains_element','variant_of','same_as');

CREATE TABLE source_system (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  base_uri text,
  revision text,
  captured_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE party (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name text NOT NULL,
  party_type text NOT NULL CHECK (party_type IN ('person','organization','unknown')),
  contact jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE source_record (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_system_id uuid REFERENCES source_system(id),
  source_type text NOT NULL CHECK (source_type IN ('fieldwork','partner','book','web','archive','generated','unknown')),
  source_uri text,
  citation text,
  collector_party_id uuid REFERENCES party(id),
  collected_at timestamptz,
  location_text text,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE pattern (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_name text NOT NULL,
  description text,
  cultural_meaning text,
  taboo_notes text,
  origin_claim text NOT NULL DEFAULT 'unknown' CHECK (origin_claim IN ('traditional','contemporary','generated','mixed','unknown')),
  status record_status NOT NULL DEFAULT 'draft',
  visibility visibility_level NOT NULL DEFAULT 'private',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pattern_alias (
  pattern_id uuid NOT NULL REFERENCES pattern(id) ON DELETE CASCADE,
  alias text NOT NULL,
  language_code text NOT NULL DEFAULT 'zh-CN',
  is_preferred boolean NOT NULL DEFAULT false,
  PRIMARY KEY (pattern_id, alias, language_code)
);

CREATE TABLE taxonomy_term (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scheme text NOT NULL,
  code text NOT NULL,
  label text NOT NULL,
  parent_id uuid REFERENCES taxonomy_term(id),
  definition text,
  active boolean NOT NULL DEFAULT true,
  UNIQUE (scheme, code)
);

CREATE TABLE pattern_term (
  pattern_id uuid NOT NULL REFERENCES pattern(id) ON DELETE CASCADE,
  term_id uuid NOT NULL REFERENCES taxonomy_term(id),
  confidence numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
  assertion_status record_status NOT NULL DEFAULT 'draft',
  asserted_by uuid REFERENCES party(id),
  PRIMARY KEY (pattern_id, term_id)
);

CREATE TABLE asset (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern_id uuid REFERENCES pattern(id) ON DELETE SET NULL,
  source_record_id uuid REFERENCES source_record(id),
  role asset_role NOT NULL DEFAULT 'source',
  object_key text NOT NULL UNIQUE,
  original_filename text NOT NULL,
  mime_type text,
  byte_size bigint NOT NULL CHECK (byte_size >= 0),
  sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  perceptual_hash text,
  width integer CHECK (width > 0),
  height integer CHECK (height > 0),
  crop_box jsonb,
  status record_status NOT NULL DEFAULT 'draft',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (sha256, role, object_key)
);
CREATE INDEX asset_sha256_idx ON asset (sha256);
CREATE INDEX asset_pattern_idx ON asset (pattern_id);

CREATE TABLE rights_record (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id uuid REFERENCES asset(id) ON DELETE CASCADE,
  pattern_id uuid REFERENCES pattern(id) ON DELETE CASCADE,
  rights_holder_id uuid REFERENCES party(id),
  legal_basis text NOT NULL DEFAULT 'unverified',
  allow_display boolean NOT NULL DEFAULT false,
  allow_download boolean NOT NULL DEFAULT false,
  allow_commercial boolean NOT NULL DEFAULT false,
  allow_ai_training boolean NOT NULL DEFAULT false,
  allow_derivatives boolean NOT NULL DEFAULT false,
  territory text,
  valid_from date,
  valid_until date,
  agreement_object_key text,
  verified_at timestamptz,
  verified_by uuid REFERENCES party(id),
  CHECK (asset_id IS NOT NULL OR pattern_id IS NOT NULL),
  CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from)
);

CREATE TABLE pattern_relation (
  from_pattern_id uuid NOT NULL REFERENCES pattern(id) ON DELETE CASCADE,
  to_pattern_id uuid NOT NULL REFERENCES pattern(id) ON DELETE CASCADE,
  kind relation_kind NOT NULL,
  notes text,
  PRIMARY KEY (from_pattern_id, to_pattern_id, kind),
  CHECK (from_pattern_id <> to_pattern_id)
);

CREATE TABLE review (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern_id uuid REFERENCES pattern(id) ON DELETE CASCADE,
  asset_id uuid REFERENCES asset(id) ON DELETE CASCADE,
  review_type text NOT NULL CHECK (review_type IN ('data_quality','cultural','rights')),
  decision record_status NOT NULL,
  reviewer_id uuid REFERENCES party(id),
  notes text,
  reviewed_at timestamptz NOT NULL DEFAULT now(),
  CHECK (pattern_id IS NOT NULL OR asset_id IS NOT NULL)
);

CREATE TABLE record_version (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  entity_type text NOT NULL CHECK (entity_type IN ('pattern','asset','rights_record','taxonomy_term')),
  entity_id uuid NOT NULL,
  version_no integer NOT NULL CHECK (version_no > 0),
  snapshot jsonb NOT NULL,
  change_reason text,
  changed_by uuid REFERENCES party(id),
  changed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_type, entity_id, version_no)
);

CREATE TABLE legacy_mapping (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_system_id uuid NOT NULL REFERENCES source_system(id),
  legacy_type text NOT NULL,
  legacy_id text NOT NULL,
  pattern_id uuid REFERENCES pattern(id),
  asset_id uuid REFERENCES asset(id),
  raw_record jsonb NOT NULL,
  imported_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_system_id, legacy_type, legacy_id)
);

CREATE TABLE model_annotation (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  asset_id uuid NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
  task text NOT NULL,
  label jsonb NOT NULL,
  annotation_version text NOT NULL,
  annotator_id uuid REFERENCES party(id),
  split text CHECK (split IN ('train','validation','test','holdout')),
  confidence numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
