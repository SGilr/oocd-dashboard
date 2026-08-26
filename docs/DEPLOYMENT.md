# Deployment

The site is a static build deployed by Cloudflare Pages from the GitHub
repository, using the git integration rather than a Wrangler API token. There is
no Worker, no database, no runtime API and no secret to leak.

This file records the settings, because the Cloudflare project could not be
created from the environment this repository was built in. Anyone with access to
the Cloudflare account can create it from what is written here in about five
minutes.

## Create the Pages project

1. In the Cloudflare dashboard, go to Workers and Pages, then Create, then
   Pages, then Connect to Git.
2. Select the GitHub repository and authorise Cloudflare for it.
3. Set the production branch to the repository's default branch.
4. Set the build settings:

   | Setting | Value |
   | --- | --- |
   | Framework preset | Astro |
   | Build command | `cd site && npm ci && npm run build` |
   | Build output directory | `site/dist` |
   | Root directory | repository root |
   | Node version | 22 |

   The build command runs `scripts/stage-data.mjs` first, through the `prebuild`
   script, which copies `data/processed/` into `site/public/data/` and writes the
   provenance and checksums the data page shows.

5. Add one environment variable, for production and for previews:

   | Name | Value |
   | --- | --- |
   | `SITE_URL` | `https://oocd.howpreventionworks.com` |

   It sets the canonical URL and the sitemap origin. Without it the build falls
   back to the `pages.dev` address, which is correct for a preview and wrong for
   production.

6. Deploy. Every push to the default branch publishes production, and every pull
   request gets its own preview URL.

## What is committed

`data/processed/` and `data/manifest.json` are committed, and so is
`data/validation-report.json`. The site renders the report on its data and
methodology pages, and Cloudflare builds from the repository, so a report that
is not committed means those sections come up empty on the deployed site.

`data/raw/` is not committed. It is rebuilt from the manifest, and the checksums
confirm a rebuild produced the same bytes.

## Before the first production deploy

The build succeeds whether or not the data is real, which is deliberate: the site
has to be reviewable before the extract runs. Confirm all four of these before
pointing a custom domain at it.

- `data/manifest.json` records `"provenance": "home_office_open_data"`, not
  `"fixture"`. A fixture build puts a red banner on every page saying the
  figures are invented.
- `python etl/validate.py --check-urls` passes, and every annotation in
  `etl/annotations.yml` has `source_url_verified: true`.
- `etl/reconciliation.yml` holds at least one headline figure read from a Home
  Office bulletin, and the reconciliation check passes.
- The `/data` page lists the real source files with their URLs and checksums.

## Custom domain

The site is served at **oocd.howpreventionworks.com**, a subdomain of the
`howpreventionworks.com` zone, which is already on Cloudflare.

In the Pages project, go to Custom domains, Set up a custom domain, and enter
`oocd.howpreventionworks.com`. Because the zone is on the same Cloudflare
account, the CNAME is created for you and the certificate is issued
automatically. Nothing needs adding to DNS by hand.

The subdomain appears in exactly two places in this repository, and they must
agree with what the Pages project serves:

- `site` in `site/astro.config.mjs`, which sets the canonical URL and the
  sitemap origin. It reads `SITE_URL` from the environment first, so the
  variable in the Pages project wins.
- The `Sitemap:` line in `site/public/robots.txt`.

To move the site to a different subdomain, change those two and the `SITE_URL`
variable.

## Headers

`site/public/_headers` is deployed by Cloudflare Pages as written. It sets a
Content Security Policy with `default-src 'none'`, `X-Content-Type-Options`,
`Referrer-Policy`, a `Permissions-Policy` that turns off every feature the site
does not use, and cache headers for the data downloads and the hashed assets.

The policy allows scripts from `static.cloudflareinsights.com` and connections to
`cloudflareinsights.com`, which is what Cloudflare Web Analytics needs. If
analytics is not enabled, remove those two entries and the policy tightens to the
site's own origin alone.

## Analytics

Enable Cloudflare Web Analytics on the Pages project. It sets no cookies, needs
no consent banner, and Cloudflare injects it at the edge, so nothing is added to
the repository.

There is no third party analytics on this site, no third party fonts, and no
trackers. The Content Security Policy above enforces that: adding one would break
the site rather than pass unnoticed.

## Refresh

`.github/workflows/etl-refresh.yml` runs quarterly. It reruns fetch, transform
and validate, and opens a pull request when the derived tables change, with the
validation report and a summary of the diff in the body. It never pushes to the
default branch. Merging the pull request triggers the Cloudflare production
deploy in the usual way.

If this directory has been kept inside a larger repository rather than split out
into its own, the workflows will not run: GitHub only reads `.github/workflows/`
at the repository root. See the note on extracting the project in `README.md`.
