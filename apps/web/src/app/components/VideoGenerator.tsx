"use client";

import { useEffect, useState } from "react";
import { createRenderJob } from "../actions";
import { supabase } from "@/lib/supabase";
import { RealtimeChannel } from "@supabase/supabase-js";

type RenderJobStatus =
  | "queued"
  | "processing_pipeline"
  | "manifest_ready"
  | "rendering_video"
  | "complete"
  | "failed";

interface StatusConfig {
  label: string;
  progress: number;
}

const STATUS_MAP: Record<RenderJobStatus, StatusConfig | ((progress: number, errorMessage?: string) => StatusConfig)> = {
  queued: { label: "Uploading your PDF...", progress: 0 },
  processing_pipeline: (progress: number) => ({
    label: "Processing your content...",
    progress: progress || 10,
  }),
  manifest_ready: { label: "Preparing video render engine...", progress: 90 },
  rendering_video: { label: "Rendering your video frames with Remotion...", progress: 95 },
  complete: { label: "Your video is ready!", progress: 100 },
  failed: (progress: number, errorMessage?: string) => ({
    label: errorMessage || "Something went wrong. Please try again.",
    progress: progress || 0,
    isError: true,
  }),
};

function getStatusConfig(status: RenderJobStatus, progress: number, errorMessage?: string): StatusConfig {
  const mapper = STATUS_MAP[status];
  if (typeof mapper === "function") {
    return mapper(progress, errorMessage);
  }
  return mapper;
}

export default function VideoGenerator() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<RenderJobStatus | "">("");
  const [progress, setProgress] = useState(0);
  const [label, setLabel] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | "">("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let channel: RealtimeChannel;

    if (jobId) {
      channel = supabase
        .channel(`job-${jobId}`)
        .on(
          "postgres_changes",
          {
            event: "UPDATE",
            schema: "public",
            table: "render_jobs",
            filter: `id=eq.${jobId}`,
          },
          (payload) => {
            const newStatus = payload.new.status as RenderJobStatus;
            const newProgress = payload.new.progress as number;
            const newErrorMessage = payload.new.error_message as string | null;

            setStatus(newStatus);
            if (payload.new.video_url) {
              setVideoUrl(payload.new.video_url as string);
            }
            if (newProgress !== undefined && newProgress !== null) {
              setProgress(newProgress);
            }
            if (newErrorMessage) {
              setErrorMessage(newErrorMessage);
            }

            const config = getStatusConfig(newStatus, newProgress ?? progress, newErrorMessage ?? undefined);
            setLabel(config.label);
          }
        )
        .subscribe();
    }

    return () => {
      if (channel) supabase.removeChannel(channel);
    };
  }, [jobId]);

  const handleGenerate = async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const id = await createRenderJob();
      setJobId(id);
      setStatus("queued");
      setProgress(0);
      setLabel("Uploading your PDF...");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "600px", margin: "0 auto", padding: "2rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "1.5rem" }}>
        VisualNote Studio
      </h1>

      <button
        onClick={handleGenerate}
        disabled={loading}
        style={{
          padding: "0.75rem 1.5rem",
          fontSize: "1rem",
          backgroundColor: "#6366F1",
          color: "#fff",
          border: "none",
          borderRadius: "8px",
          cursor: loading ? "not-allowed" : "pointer",
          opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? "Generating..." : "Generate Video"}
      </button>

      {status && (
        <div style={{ marginTop: "2rem" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: "0.5rem",
              fontSize: "0.875rem",
              color: "#A0A0B0",
            }}
          >
            <span>{label}</span>
            <span>{progress}%</span>
          </div>

          <div
            style={{
              width: "100%",
              height: "8px",
              backgroundColor: "#1F1F3D",
              borderRadius: "4px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${progress}%`,
                height: "100%",
                backgroundColor: status === "failed" ? "#EF4444" : "#6366F1",
                borderRadius: "4px",
                transition: "width 0.3s ease-out",
              }}
            />
          </div>
        </div>
      )}

      {status === "failed" && errorMessage && (
        <div
          style={{
            marginTop: "1rem",
            padding: "1rem",
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            border: "1px solid #EF4444",
            borderRadius: "8px",
            color: "#FCA5A5",
            fontSize: "0.875rem",
          }}
        >
          {errorMessage}
        </div>
      )}

      {videoUrl && (
        <div style={{ marginTop: "2rem" }}>
          <video
            src={videoUrl}
            controls
            muted
            autoPlay
            loop
            style={{ width: "100%", borderRadius: "8px" }}
          />
        </div>
      )}
    </div>
  );
}