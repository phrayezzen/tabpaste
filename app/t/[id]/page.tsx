"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Status } from "@/components/status";

// Dynamic import TabViewer to avoid SSR issues with alphaTab
const TabViewer = dynamic(
  () => import("@/components/tab-viewer").then((mod) => mod.TabViewer),
  { ssr: false }
);

interface JobData {
  id: string;
  youtube_url: string;
  video_title: string | null;
  status: string;
  status_detail: string | null;
  error: string | null;
  musicXmlUrl?: string;
}

const POLL_INTERVAL = 1500; // 1.5 seconds

export default function ResultPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.id as string;

  const [job, setJob] = useState<JobData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchJob = useCallback(async () => {
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      if (!response.ok) {
        if (response.status === 404) {
          setError("Job not found");
          return false;
        }
        throw new Error("Failed to fetch job status");
      }
      const data = await response.json();
      setJob(data);
      setLoading(false);

      // Return true if we should continue polling
      return data.status !== "done" && data.status !== "failed";
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
      setLoading(false);
      return false;
    }
  }, [jobId]);

  useEffect(() => {
    let mounted = true;
    let timeoutId: NodeJS.Timeout;

    const poll = async () => {
      if (!mounted) return;

      const shouldContinue = await fetchJob();

      if (mounted && shouldContinue) {
        timeoutId = setTimeout(poll, POLL_INTERVAL);
      }
    };

    poll();

    return () => {
      mounted = false;
      clearTimeout(timeoutId);
    };
  }, [fetchJob]);

  const handleDownloadMusicXml = () => {
    if (job?.musicXmlUrl) {
      const a = document.createElement("a");
      a.href = job.musicXmlUrl;
      a.download = `${job.video_title || "tab"}.musicxml`;
      a.click();
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (error) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center min-h-screen bg-zinc-50 dark:bg-zinc-950 p-6">
        <div className="text-center space-y-4">
          <p className="text-red-500">{error}</p>
          <Link href="/">
            <Button>Try another URL</Button>
          </Link>
        </div>
      </div>
    );
  }

  if (loading || !job) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center min-h-screen bg-zinc-50 dark:bg-zinc-950">
        <div className="flex items-center gap-2">
          <span className="animate-pulse">●</span>
          <span className="text-muted-foreground">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b bg-white dark:bg-zinc-900 print:hidden">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="font-semibold text-lg">
            TabPaste
          </Link>
          {job.status === "done" && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={handleDownloadMusicXml}>
                Download MusicXML
              </Button>
              <Button variant="outline" size="sm" onClick={handlePrint}>
                Print PDF
              </Button>
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
        {job.status === "done" && job.musicXmlUrl ? (
          <TabViewer musicXmlUrl={job.musicXmlUrl} title={job.video_title || undefined} />
        ) : job.status === "failed" ? (
          <div className="flex flex-col items-center justify-center py-16 space-y-6">
            <Status status={job.status} statusDetail={job.status_detail} error={job.error} />
            <Link href="/">
              <Button>Try another URL</Button>
            </Link>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 space-y-4">
            {job.video_title && (
              <h2 className="text-xl font-medium text-zinc-900 dark:text-zinc-100">
                {job.video_title}
              </h2>
            )}
            <Status status={job.status} statusDetail={job.status_detail} error={job.error} />
          </div>
        )}
      </main>
    </div>
  );
}
