"use client";

interface StatusProps {
  status: string;
  statusDetail?: string | null;
  error?: string | null;
}

export function Status({ status, statusDetail, error }: StatusProps) {
  if (status === "failed" && error) {
    return (
      <div className="text-center space-y-2">
        <p className="text-red-500 font-medium">Processing failed</p>
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (status === "done") {
    return (
      <p className="text-green-600 font-medium">Tablature ready!</p>
    );
  }

  // Processing states
  const displayText = statusDetail || getDefaultText(status);

  return (
    <div className="flex items-center gap-2">
      <span className="animate-pulse">●</span>
      <p className="text-muted-foreground">{displayText}</p>
    </div>
  );
}

function getDefaultText(status: string): string {
  switch (status) {
    case "queued":
      return "Waiting in queue...";
    case "processing":
      return "Processing...";
    default:
      return "Working...";
  }
}
