// @ts-check
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

// Static output. Every figure on the site is baked at build time from the
// derived tables in data/processed, so the deployed site makes no data request
// of its own and there is no runtime to secure.
export default defineConfig({
  site: process.env.SITE_URL || "https://oocd-dashboard.pages.dev",
  output: "static",
  trailingSlash: "ignore",
  build: { format: "directory", inlineStylesheets: "auto" },
  devToolbar: { enabled: false },
  integrations: [sitemap()],
});
