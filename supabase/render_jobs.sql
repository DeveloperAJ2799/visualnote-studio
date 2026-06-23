-- Supabase SQL for render_jobs table

CREATE TYPE render_job_status AS ENUM (
  'queued',
  'processing_pipeline',
  'manifest_ready',
  'rendering_video',
  'complete',
  'failed'
);

CREATE TABLE render_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  user_id UUID,
  pdf_url TEXT,
  manifest_url TEXT,
  video_url TEXT,
  status render_job_status DEFAULT 'queued',
  progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  error_message TEXT
);

ALTER TABLE render_jobs ENABLE ROW LEVEL SECURITY;