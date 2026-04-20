import { UrlInput } from "@/components/url-input";

export default function Home() {
  return (
    <div className="flex flex-col flex-1 items-center justify-center min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <main className="flex flex-col items-center gap-8 px-6 text-center">
        <div className="space-y-2">
          <h1 className="text-4xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            TabPaste
          </h1>
          <p className="text-lg text-zinc-600 dark:text-zinc-400">
            Convert YouTube fingerstyle guitar to tablature
          </p>
        </div>

        <UrlInput />

        <p className="max-w-md text-sm text-zinc-500 dark:text-zinc-500">
          Solo fingerstyle guitar only. No vocals, no band mixes.
        </p>
      </main>
    </div>
  );
}
