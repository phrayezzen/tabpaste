import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase-server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const supabase = createServerClient();

    // Fetch job
    const { data: job, error: fetchError } = await supabase
      .from("jobs")
      .select("*")
      .eq("id", id)
      .single();

    if (fetchError || !job) {
      return NextResponse.json(
        { error: "Job not found" },
        { status: 404 }
      );
    }

    // If job is done and has musicxml_path, create a signed URL
    let musicXmlUrl: string | null = null;
    if (job.status === "done" && job.musicxml_path) {
      const { data: signedUrlData, error: signedUrlError } = await supabase
        .storage
        .from("tabs")
        .createSignedUrl(job.musicxml_path, 3600); // 1 hour expiry

      if (signedUrlError) {
        console.error("Failed to create signed URL:", signedUrlError);
      } else {
        musicXmlUrl = signedUrlData.signedUrl;
      }
    }

    return NextResponse.json({
      id: job.id,
      youtube_url: job.youtube_url,
      video_title: job.video_title,
      status: job.status,
      status_detail: job.status_detail,
      error: job.error,
      musicXmlUrl,
    });
  } catch (error) {
    console.error("Error fetching job:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
