import { supabase } from "@/lib/supabase";

export async function createRenderJob() {
  const { data, error } = await supabase
    .from("render_jobs")
    .insert({ pdf_url: "https://example.com/dummy.pdf", status: "queued" })
    .select()
    .single();

  if (error) throw new Error(error.message);

  await fetch(process.env.PIPELINE_CLOUD_RUN_URL!, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: data.id, pdf_url: data.pdf_url }),
  });

  return data.id;
}