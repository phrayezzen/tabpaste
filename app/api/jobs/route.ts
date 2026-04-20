import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase-server";

const YOUTUBE_URL_REGEX = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)[a-zA-Z0-9_-]+/;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { youtubeUrl } = body;

    // Validate URL
    if (!youtubeUrl || typeof youtubeUrl !== "string") {
      return NextResponse.json(
        { error: "YouTube URL is required" },
        { status: 400 }
      );
    }

    if (!YOUTUBE_URL_REGEX.test(youtubeUrl.trim())) {
      return NextResponse.json(
        { error: "Invalid YouTube URL" },
        { status: 400 }
      );
    }

    const supabase = createServerClient();

    // Create job record
    const { data: job, error: insertError } = await supabase
      .from("jobs")
      .insert({ youtube_url: youtubeUrl.trim() })
      .select("id")
      .single();

    if (insertError || !job) {
      console.error("Failed to create job:", insertError);
      return NextResponse.json(
        { error: "Failed to create job" },
        { status: 500 }
      );
    }

    // Fire-and-forget: trigger Modal processing
    const modalEndpoint = process.env.MODAL_ENDPOINT_URL;
    if (modalEndpoint) {
      // Don't await - fire and forget
      fetch(modalEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job.id,
          youtube_url: youtubeUrl.trim(),
        }),
      }).catch((err) => {
        console.error("Failed to trigger Modal:", err);
      });
    } else {
      console.warn("MODAL_ENDPOINT_URL not configured");
    }

    return NextResponse.json({ jobId: job.id });
  } catch (error) {
    console.error("Error creating job:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
