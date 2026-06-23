import { NextRequest, NextResponse } from "next/server";
import { renderMediaOnLambda, getRenderProgress } from "@remotion/lambda";
import { supabase } from "@/lib/supabase";

export const dynamic = "force-dynamic";

interface RenderRequest {
  job_id: string;
  manifest_url: string;
}

const REMOTION_SERVE_URL = process.env.REMOTION_SERVE_URL!;
const REMOTION_FUNCTION_NAME = process.env.REMOTION_APP_FUNCTION_NAME!;
const AWS_REGION = process.env.REMOTION_AWS_REGION!;

async function pollRenderProgress(
  renderId: string,
  bucketName: string,
  jobId: string
): Promise<void> {
  const poll = async (): Promise<void> => {
    const progress = await getRenderProgress({
      renderId,
      bucketName,
      functionName: REMOTION_FUNCTION_NAME,
    });

    if (progress.status === "completed") {
      const outName = progress.out !== undefined ? progress.out : "out.mp4";
      const videoUrl = `https://${bucketName}.s3.${AWS_REGION}.amazonaws.com/${outName}`;

      await supabase
        .from("render_jobs")
        .update({
          status: "complete",
          video_url: videoUrl,
        })
        .eq("id", jobId);

      return;
    }

    if (progress.status === "failed") {
      const errorLog =
        progress.errors?.map((e) => e.stack || e.value).join("\n") ||
        "Render failed";

      await supabase
        .from("render_jobs")
        .update({
          status: "failed",
          error_message: errorLog.slice(0, 1000),
        })
        .eq("id", jobId);

      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 5000));
    return poll();
  };

  return poll();
}

export async function POST(req: NextRequest) {
  try {
    const body: RenderRequest = await req.json();
    const { job_id, manifest_url } = body;

    if (!job_id || !manifest_url) {
      return NextResponse.json(
        { error: "Missing job_id or manifest_url" },
        { status: 400 }
      );
    }

    await supabase
      .from("render_jobs")
      .update({ status: "rendering_video" })
      .eq("id", job_id);

    const { renderId, bucketName } = await renderMediaOnLambda({
      functionName: REMOTION_FUNCTION_NAME,
      region: AWS_REGION,
      serveUrl: REMOTION_SERVE_URL,
      composition: "VideoComposition",
      inputProps: { manifest_url },
      outName: "output.mp4",
      codec: "h264",
    });

    setTimeout(() => {
      pollRenderProgress(renderId, bucketName, job_id).catch(console.error);
    }, 0);

    return NextResponse.json({
      status: "rendering",
      render_id: renderId,
      bucket: bucketName,
    });
  } catch (error) {
    console.error("Render API error:", error);
    return NextResponse.json(
      { error: "Failed to start render" },
      { status: 500 }
    );
  }
}