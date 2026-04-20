"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const YOUTUBE_URL_REGEX = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)[a-zA-Z0-9_-]+/;

export function UrlInput() {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    const trimmedUrl = url.trim();

    if (!trimmedUrl) {
      setError("Please enter a YouTube URL");
      return;
    }

    if (!YOUTUBE_URL_REGEX.test(trimmedUrl)) {
      setError("Please enter a valid YouTube URL");
      return;
    }

    startTransition(async () => {
      try {
        const response = await fetch("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ youtubeUrl: trimmedUrl }),
        });

        const data = await response.json();

        if (!response.ok) {
          setError(data.error || "Failed to create job");
          return;
        }

        router.push(`/t/${data.jobId}`);
      } catch {
        setError("Failed to submit. Please try again.");
      }
    });
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-xl space-y-4">
      <div className="flex gap-2">
        <Input
          type="url"
          placeholder="Paste YouTube URL here..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={isPending}
          autoFocus
          className="flex-1"
        />
        <Button type="submit" disabled={isPending}>
          {isPending ? "..." : "Convert"}
        </Button>
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
    </form>
  );
}
