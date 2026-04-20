import type { NextConfig } from "next";
import { copyFileSync, mkdirSync, readdirSync, existsSync } from "fs";
import { join } from "path";

// Copy alphaTab fonts to public folder at build time
const alphaTabFontDir = join(process.cwd(), "node_modules/@coderline/alphatab/dist/font");
const publicFontDir = join(process.cwd(), "public/font");

if (existsSync(alphaTabFontDir)) {
  mkdirSync(publicFontDir, { recursive: true });
  const fontFiles = readdirSync(alphaTabFontDir);
  for (const file of fontFiles) {
    copyFileSync(join(alphaTabFontDir, file), join(publicFontDir, file));
  }
}

const nextConfig: NextConfig = {
  // Enable Turbopack (Next.js 16 default)
  turbopack: {},
};

export default nextConfig;
