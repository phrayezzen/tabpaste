"use client";

import { useEffect, useRef, useState } from "react";

interface TabViewerProps {
  musicXmlUrl: string;
  title?: string;
}

export function TabViewer({ musicXmlUrl, title }: TabViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let api: unknown = null;

    async function loadTab() {
      if (!containerRef.current) return;

      try {
        // Dynamic import to avoid SSR issues
        const alphaTab = await import("@coderline/alphatab");

        // Fetch the MusicXML content
        const response = await fetch(musicXmlUrl);
        if (!response.ok) {
          throw new Error("Failed to fetch tablature");
        }
        const arrayBuffer = await response.arrayBuffer();

        // Initialize alphaTab
        const settings = new alphaTab.Settings();
        settings.core.fontDirectory = "/font/";
        settings.core.engine = "svg";
        settings.display.staveProfile = alphaTab.StaveProfile.Tab;
        settings.display.layoutMode = alphaTab.LayoutMode.Page;
        settings.player.enablePlayer = false;

        api = new alphaTab.AlphaTabApi(containerRef.current, settings);

        // Load the MusicXML
        (api as { load: (data: Uint8Array) => void }).load(new Uint8Array(arrayBuffer));

        // Listen for render completion
        (api as { renderFinished: { on: (cb: () => void) => void } }).renderFinished.on(() => {
          setLoading(false);
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load tablature");
        setLoading(false);
      }
    }

    loadTab();

    return () => {
      if (api && typeof (api as { destroy?: () => void }).destroy === "function") {
        (api as { destroy: () => void }).destroy();
      }
    };
  }, [musicXmlUrl]);

  if (error) {
    return (
      <div className="p-4 border border-red-200 rounded bg-red-50">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  return (
    <div className="w-full">
      {title && (
        <h2 className="text-xl font-semibold mb-4">{title}</h2>
      )}
      {loading && (
        <div className="flex items-center gap-2 mb-4">
          <span className="animate-pulse">●</span>
          <span className="text-muted-foreground">Rendering tablature...</span>
        </div>
      )}
      <div
        ref={containerRef}
        className="w-full min-h-[400px] bg-white"
        style={{ visibility: loading ? "hidden" : "visible" }}
      />
    </div>
  );
}
