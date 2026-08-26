# Capacity Page: Work Order

**For:** Claude Code, working in Stan Gilmour's repository for `oocd.howpreventionworks.com`
**From:** Oxon Advisory, De Montfort University out of court disposals review
**Date:** 26 August 2026
**Companion documents in the DMU OOCD project:** `claude/prison-demand-claim-evidence-check.md`, `claude/oocd-prison-demand-page-brief.md`

---

> **Read Appendix E first.** The environment was inspected on 26 August 2026 and the site turned out to be an Astro build behind a strict content security policy, not the hand-written static site this document originally assumed. Appendix E overrides Steps 2 and 5 where they conflict.

## What you are being asked to do

**Add one page to the site that already exists at `https://oocd.howpreventionworks.com`.** You built that site in an earlier session. This is an addition to it, and nothing else.

To be unambiguous, because the distinction decides everything in Step 1:

- **This is:** a new page added to the existing oocd site, deployed by redeploying that site with the page in it.
- **This is not:** a new site, a new Worker, a new Cloudflare project, or a replacement for what is live. The existing pages stay exactly as they are, at the URLs they already have.

The page carries a live prison capacity panel, a demand cascade, a reverse-solve calculator and an evidence section. It is static: no build step, no framework, no dependencies beyond Google Fonts.

You will also add a scheduled GitHub Action that refreshes the capacity figures weekly from published Ministry of Justice data, and a headers file so the refreshed figures are not held in an edge cache.

The files are supplied. Your job is to place them correctly in the existing repository, wire up the automation, confirm one parser detail that could not be confirmed at authoring time, and deploy.

## Standing constraints

These are not stylistic preferences. Each one exists because the page makes a contested claim about evidence and has to survive a hostile reader.

1. **Do not add a forward estimate.** The calculator deliberately runs backwards: the reader sets a target in prison places and it derives the diversion volume that target implies. It must never output "increase diversion by x and save y places". No published estimate of that relationship exists, and a forward number would be quoted as a forecast the moment it left the page.
2. **Do not add a savings counter.** The cost per prison place is not cash-realisable at the margin. A ticking money figure would be the weakest thing on the page.
3. **Preserve the colour semantics.** Ink means measured, rust means modelled. Every figure in ink traces to a published source named in the notes. Every figure in rust is produced by the calculator from parameters the reader set. Do not use the rust colour for decoration, headings or emphasis anywhere else on the page.
4. **Do not invent, round up or fill in any figure.** If a number is missing, leave the gap and say so. Several gaps on this page are deliberate, and the section headed "Three parameters the public evidence base does not contain" is an argument, not an oversight.
5. **UK English throughout, sentence case for subheadings, Title Case for main headings, no em dashes, metric units.** This applies to commit messages and code comments as well as visible copy.

## What is already on the machine, established 26 August 2026

This was checked rather than assumed. Take it as the starting position and verify anything that has moved.

- `~/projects` contains `BRAID`, `ailt-backup-2026-05-19`, `cairn`, `cairn-public`, `faire`, `prism-r` and `stair`. Only `prism-r` has a git remote configured, at `github.com/SGilr/prism-r.git`. The others are local repositories or working folders without an origin.
- **The oocd project is not under `~/projects`.** Nothing there matches `oocd`, and nothing there references `oocd.howpreventionworks.com`. Only `~/projects` was searched, because that was the only folder granted to the session that assembled this kit. The source almost certainly exists somewhere: you created the site yourself in an earlier session, so check your own project history and prior working directories, then `~/Desktop`, `~/Downloads` and anywhere else you habitually put a small static site, before concluding it is unrecoverable. Finding it is Step 1 and it is the first thing to report back.
- The `howpreventionworks.com` zone is active on the Cloudflare account, and subdomains on it are served by **Workers with static assets, not by Cloudflare Pages**. The working example is `BRAID/dhr-analysis-tool/wrangler.toml`, which routes `dardr.howpreventionworks.com` with `custom_domain = true` and `zone_name = "howpreventionworks.com"`, so Cloudflare provisions DNS and TLS on deploy.
- The static asset pattern in use is the one in `stair/wrangler.toml`: `[assets]` with `directory = "./public"` and `binding = "ASSETS"`. Assume the oocd project follows it until you see otherwise.
- The kit is at `~/projects/oocd-capacity-kit/`. It sits beside the repositories rather than inside one, deliberately, so nothing lands in a repository before Step 1 is done.

## Prerequisites you will need from the environment

- Read and write access to `~/projects`, which holds the kit and the repositories.
- Git access to push to that repository.
- Cloudflare access sufficient to list Workers and Pages projects on the account holding the `howpreventionworks.com` zone, to see their routes, and to purge cache if needed. An authenticated `wrangler` is the quickest route.
- Python 3.10 or later locally, to run the ingest script once by hand.

If any of these is missing, stop and say which one rather than working around it.

---

## Step 1: Find the project that serves oocd.howpreventionworks.com

The site is live. Something already serves it, and that something is not on this machine. Do not deploy anything to that hostname until you know what you would be replacing.

You built this site. Start with your own history rather than with Cloudflare: the working directory of the session that created it is the fastest route to the source, and it will also tell you the project name and the deployment command that was used.

If that does not find it, work through these in order and stop at the first that answers the question:

1. Confirm which account you are authenticated against with `npx wrangler whoami`, then open the Workers and Pages list for the account holding the `howpreventionworks.com` zone, or check the zone's DNS records for the hostname. Identify the project bound to `oocd.howpreventionworks.com`, its name, and whether it has a connected git repository. Once you have the name, `npx wrangler deployments list --name <worker>` gives you its deployment history.
2. If it is connected to a repository, clone that repository into `~/projects/` and work in it.
3. If the source genuinely cannot be recovered, say so plainly and stop. Reconstructing the site from its deployed assets and redeploying it is a reasonable option, but it risks losing pages or behaviour you cannot see from the outside, so it is Stan's decision and not yours. Do not start a fresh project on that route as a workaround.

**The hard rule: do not run `wrangler deploy` against a `wrangler.toml` carrying a `custom_domain` route for `oocd.howpreventionworks.com` until you have confirmed you are deploying the existing project rather than a new one that would take the route from it.**

Once you have the project, establish:

- The assets directory. On this account's pattern that is `./public`, declared under `[assets]` in `wrangler.toml`.
- Whether an `index.html` already exists at the assets root. If it does, this page is an addition and not a replacement. Put it at `public/capacity/index.html` so it serves at `/capacity`, and tell Stan the URL you chose.
- Whether the Worker has a `fetch` handler that intercepts requests before the asset binding, which would change how the page and its JSON are served.
- Whether a `_headers` file already exists in the assets directory. If so, merge the new rules into it rather than replacing it.

Report what you found before proceeding.

## Step 2: Place the files

Everything below is in `~/projects/oocd-capacity-kit/`:

```
capacity.md                            this document
index.html                             the page
data/prison-capacity.json              seed figures, replaced weekly by the Action
scripts/fetch_prison_figures.py        the ingest, standard library only
.github/workflows/prison-figures.yml   the weekly schedule
_headers                               cache rules for the static assets
README.md                              developer notes, not for publication
```

Placement, assuming the Workers static assets pattern with `directory = "./public"`:

| Kit file | Destination |
|---|---|
| `index.html` | `public/index.html`, or `public/capacity/index.html` if the root is taken |
| `data/prison-capacity.json` | `public/data/prison-capacity.json`, or `public/capacity/data/...` to match |
| `_headers` | the assets root, `public/_headers` |
| `scripts/fetch_prison_figures.py` | `scripts/` at the repository root, outside the assets directory |
| `.github/workflows/prison-figures.yml` | `.github/workflows/` at the repository root |
| `README.md` | repository root as `DEVELOPER-NOTES.md`, outside the assets directory |
| `capacity.md` | keep in the kit folder, or commit it to the repository root as the record |

Two rules that matter more than the table. `data/` must sit **beside** `index.html` wherever that ends up, because the page fetches `data/prison-capacity.json` at a relative path; if you move the page into a subdirectory, move its data directory with it. And `scripts/` must sit outside the assets directory, or the ingest script is served to the public and, more to the point, the Action writes into a path the Worker publishes.

If the ingest writes to `public/data/prison-capacity.json`, update `OUT_PATH` at the top of `scripts/fetch_prison_figures.py` to match. It currently resolves to `data/prison-capacity.json` relative to the repository root.

Commit these as one change with a message describing the addition, not the mechanics.

## Step 3: Confirm the parser, which is the one genuinely open item

The page reads the Ministry of Justice weekly prison estate bulletin. The route is:

1. `GET https://www.gov.uk/api/content/government/publications/prison-population-weekly-estate-figures-2026`
2. The response is JSON. `details.attachments` is an ordered list; each entry carries a title such as `Population bulletin: weekly 24 August 2026` and a direct `url` to an `.ods` file on `assets.publishing.service.gov.uk`.
3. The script downloads the newest attachment, unzips it, and parses `content.xml` with the standard library. It finds the population and capacity figures by matching row labels, not by cell coordinates, so a layout change cannot silently produce a wrong number.

**The label patterns in the script are candidates, not confirmed.** The bulletin could not be opened from the environment where this was authored, because `assets.publishing.service.gov.uk` was unreachable there. Close that loop now:

```bash
python3 scripts/fetch_prison_figures.py --dry-run
```

Read what it prints.

- If it reports a population and a capacity that look like an English and Welsh prison estate, roughly 80,000 to 95,000 each, with capacity above population, the mapping is correct. Run it without `--dry-run`, commit the resulting `data/prison-capacity.json`, and move on.
- If it reports `PARSE INCOMPLETE`, open `data/_sheet-dump.json`, which it will have written. Find the rows that actually hold those two figures, and add their labels as regular expressions to the `LABELS` dictionary at the top of `scripts/fetch_prison_figures.py`. Re-run. Repeat until clean.

**If the dry run cannot reach the network.** The staging environment this kit was assembled in could not resolve `gov.uk`, and neither could the sandbox that wrote it, so the script has never made a live request. Claude Code running on the machine itself should have no such restriction. If it does, there is a clean fallback: trigger the GitHub Action by hand from the Actions tab. It runs on GitHub's own runners with unrestricted network, and on a failed parse it commits `data/_sheet-dump.json` to the repository. Pull that commit, read the dump, extend `LABELS`, push, and trigger the Action again.

Do not remove the sanity check that rejects figures outside a plausible range, and do not remove the behaviour that keeps the previous values on a failed parse. A page showing last week's verified figure with a note is correct; a page showing a wrong figure confidently is not.

Add `data/_sheet-dump.json` to `.gitignore` once the mapping is settled, or leave it committed as an audit trail. Either is defensible. Say which you chose.

## Step 4: Enable the automation

The workflow runs at 07:15 UTC on Tuesdays, a day after the Monday publication, and can also be started by hand from the Actions tab. It declares `permissions: contents: write` and needs no secrets.

Check that the repository allows Actions to push to the default branch. In some settings this requires enabling read and write permissions for the workflow token under Settings, Actions, General.

Then trigger it once manually and confirm it either commits a change or reports no change. A failed run is informative rather than fatal: it means the parse needs attention and the page is still showing the last verified figures.

## Step 5: Cloudflare

Three things to check.

**Cache.** The kit's `_headers` file sets a five minute cache on `/data/*`. Without it the weekly figures can sit in an edge cache and the panel will show stale numbers after a successful ingest. Cloudflare Workers static assets do support `_headers`, placed in the assets directory, subject to a limit of 100 rules and 2,000 characters a line. Adjust the paths in it if you moved the page into a subdirectory.

**The Worker caveat.** Headers declared in `_headers` apply only to static asset responses. If this Worker generates any response in code rather than serving it from the asset binding, `_headers` will not touch it and the `Cache-Control` has to be set in the Worker's own response. Check which applies before assuming the cache rule took effect, and confirm it with a request to the live JSON path once deployed.

**Automated access.** The subdomain currently returns HTTP 403 to automated requests, which is consistent with Cloudflare bot protection. This does not affect the page, which is fetched by real browsers, and does not affect the Action, which talks to GOV.UK rather than to the site. Leave the setting alone. It is worth knowing about only if you verify the deployment with a headless request and get a 403 that is nothing to do with your change.

## Step 6: Verify before you call it done

Work through all of these. The first four are functional, the rest are the ones a reviewer will notice.

- The capacity panel shows a population, a capacity, a headroom figure and an occupancy percentage, and the provenance line at the foot of the panel names its source.
- Renaming `data/prison-capacity.json` temporarily makes the panel fall back to its built-in figures and say "Seed figures" rather than showing dashes or throwing. Put the file back.
- Moving the target slider changes the required volume, the four numbered checks and the verdict text. At 10,000 places the verdict should be about the counterfactual assumption, not the volume.
- Setting both the counterfactual custody share and the reoffending reduction to zero produces "no finite answer" rather than infinity or `NaN`.
- No horizontal scrolling of the page body at 390 px width. The cascade table scrolls inside its own container, which is intended.
- The theme toggle works in both directions and survives a reload, and the page respects the operating system setting when no explicit choice has been made.
- Print preview produces sensible A4 pages with the sliders hidden.
- Keyboard: every slider is reachable by tab and has a visible focus ring.
- The browser console is clean apart from any Google Fonts warning.

## Step 7: Report back

Tell Stan, in this order: the URL the page is live at, what the parser dry run returned, whether the first Action run succeeded, and anything in the verification list that did not pass. Flag anything you changed from the supplied files and why.

---

# Appendix A: The arithmetic, for anyone editing the calculator

Places removed per additional diverted case:

```
immediate  = counterfactual custody share × time served
downstream = reoffending reduction × custody rate on averted reoffences × time served
perCase    = immediate + downstream
casesNeeded = target ÷ perCase
```

All quantities are place-years per year, so a target of 1,000 means 1,000 fewer occupied places at any given moment, sustained.

The five parameters and their status as shown on the page:

| Parameter | Default | Status |
|---|---|---|
| Share of diverted cases whose sentence would have been immediate custody | 2% | No published value anywhere in England and Wales |
| Time served on each averted custodial sentence | 2 months | Derived: a six month sentence at the one third release point under the Sentencing Act 2026, in force from 1 October 2026 |
| Reduction in the proportion who reoffend | 5 pp | No published causal estimate for England and Wales |
| Custody rate applied to averted reoffences | 10% | Anchored against the published 33.5% indictable custody rate |
| Time served on averted future custodial sentences | 2 months | Derived, same basis |

On the defaults, removing 1,000 places requires about 240,000 additional out of court resolutions a year, against a current total annual volume of 226,300. That result is the argument the page exists to make.

The three published denominators the result is tested against, all hard-coded in the `MEASURED` object:

- 226,300 out of court resolutions, year to December 2025
- 88,100 immediate custodial sentences, year to December 2025
- 85,858 prison population, 30 June 2026

# Appendix B: Palette

Validated for colourblind separation and contrast in both themes. Worst all-pairs separation is Delta E 9.1 light and 8.5 dark under simulated protanopia and deuteranopia, against a target of 8, with every mark clearing 3:1 against its surface. If you change a hue, re-validate before publishing.

| Role | Light | Dark |
|---|---|---|
| Resolved out of court | `#12906a` | `#199e70` |
| Prosecuted, sentenced, imprisoned | `#2a78d6` | `#3987e5` |
| Modelled | `#b4441b` | `#e0693a` |
| Surface | `#f6f3ec` | `#16150f` |
| Ink | `#14130f` | `#f4f1e6` |

Typefaces are Fraunces for display, Archivo for interface, IBM Plex Mono for figures, all from Google Fonts with local fallbacks declared. If the site has a policy against third party font hosting, self-host them and update the `@font-face` declarations; do not substitute system fonts, because the numeric hierarchy depends on the tabular figures.

# Appendix C: Figures to confirm before this is publicised

Two items were read from a summarising fetch of the GOV.UK bulletin page rather than from the underlying tables, and should be checked against the published tables before the page is promoted:

- The year ending December 2025 sentencing figures: 1.20 million offenders sentenced, 77 per cent fines, 88,100 immediate custody, 58 per cent of custodial sentences under twelve months, 33.5 per cent indictable custody rate.
- The recorded crime total of about 5.27 million, which is a sum of about 4.4 million victim-based and 873,255 non-victim-based offences and is shown on the page as approximate for that reason.

Do not quietly correct either of these yourself. Flag any discrepancy to Stan with the table reference.

# Appendix D: Sources cited on the page

1. Home Office (2026) *Crime outcomes in England and Wales 2025 to 2026*.
2. Ministry of Justice (2026) *Criminal justice statistics quarterly: December 2025*.
3. Ministry of Justice (2026) *Offender management statistics quarterly: January to March 2026*.
4. Ministry of Justice (2026) *Prison population weekly estate figures 2026*, transparency data.
5. Ministry of Justice (2025) *Prison population projections 2025 to 2030, England and Wales*.
6. Ministry of Justice (2025) *Sentencing Bill impact assessment*, 1 September.
7. Ministry of Justice (2026) *Proven reoffending statistics: July to September 2024*.
8. House of Commons Library (2026) *Changes to automatic prisoner release dates in England and Wales*, CBP-10974.
9. National Audit Office (2024) *Increasing the capacity of the prison estate to meet demand*, HC 376.
10. HM Prison and Probation Service (2026) *Costs per place and costs per prisoner 2024-25*.
11. Mueller-Smith, M. and Schnepel, K.T. (2021) 'Diversion in the criminal justice system', *Review of Economic Studies*, 88(2), pp. 883-936.
12. Agan, A., Doleac, J.L. and Harvey, A. (2023) 'Misdemeanor prosecution', *Quarterly Journal of Economics*, 138(3), pp. 1453-1505.
13. Neyroud, P. (2018) *Out of court disposals managed by the police: a review of the evidence*. National Police Chiefs' Council.


---

# Appendix E: The environment as actually found, which overrides Steps 2 and 5

Established by inspection on 26 August 2026. Where this appendix and the earlier steps disagree, this appendix wins.

## What the site really is

`oocd.howpreventionworks.com` is served by an assets-only Cloudflare Worker named `oocd-dashboard`, configured by `wrangler.jsonc` at the root of `github.com/SGilr/oocd-dashboard`. It has no `main` entry point and runs no code. Deployment is driven by Cloudflare's git integration on push to `main`, with the build command `cd site && npm ci && npm run build` and the deploy command `npx wrangler deploy` executed by Cloudflare's own builder.

Two consequences. The Step 1 warning about taking the route with a stray `wrangler deploy` no longer applies, because there is no local deploy path; do not run `wrangler deploy` yourself at all. And the unit of work is a pull request against `main`, not a manual deploy.

The site is an Astro 5 static build. Pages are `.astro` files in `site/src/pages/`. The assets directory is `./site/dist`, which is gitignored and produced by the build. A `prebuild` step runs `check-theme-tokens.mjs` and `stage-data.mjs`, the latter copying `data/processed/` into `site/public/data/`.

## The three collisions, decided

**1. Build it as an Astro page, not as raw HTML.** Create `site/src/pages/capacity.astro` using `Layout.astro`, so it inherits the shared header, navigation, footer, theme tokens and fixture banner, and so the theme token check and the accessibility run cover it. Nothing in the Step 6 verification list depends on the file being literal static HTML. The kit's `index.html` is a reference implementation and a specification, not a file to drop in.

What must survive the port, in priority order: the epistemic colour semantics, ink for measured and rust for modelled, including the badges on the calculator parameters; the reverse-solve arithmetic and the four numbered checks; the numeric hierarchy, which depends on tabular figures; and the fallback behaviour when the data file is missing. Everything else, including the exact type scale and the surface colours, should give way to the existing design system where the two disagree. If the system's tokens do not already carry an equivalent of the modelled colour, register a new one rather than hardcoding a hex, and keep the name semantic.

**2. Merge into the existing `site/public/_headers`. Do not add a second one.** The kit's `_headers` is superseded. Take from it only what the existing file does not already cover for the path the capacity JSON ends up at.

**Then check the content security policy, because as written this page violates it.** The existing policy is `default-src 'none'` with `script-src 'self' https://static.cloudflareinsights.com`. The reference implementation carries one inline `<style>` block, one inline `<script>` block and a Google Fonts stylesheet link. Under that policy none of the three would run.

Porting to Astro solves two of them by itself: Astro extracts component styles and scripts into `/_astro/` assets served from `'self'`. The fonts are the open question. Fraunces, Archivo and IBM Plex Mono are all open licensed, so self-hosting them into `site/public/fonts/` and declaring `@font-face` locally keeps the policy untouched, which is the better outcome. Loosening the policy with `style-src https://fonts.googleapis.com` and `font-src https://fonts.gstatic.com` is the alternative. Check first whether the site already loads webfonts and how, follow that precedent if one exists, and tell Stan which route you took. Do not substitute system fonts, because the numeric hierarchy depends on the tabular figures.

**3. Add the fifth navigation item.** The hardcoded array in `site/src/components/Layout.astro` needs the new page or nobody will find it. Adding an entry does not move or change any existing page, which is what the instruction protects. Use a short label; "Capacity" is fine unless the existing labels follow another pattern.

## The data path, which needs changing from what the kit assumes

The reference implementation fetches `data/prison-capacity.json` at a relative path. That works from a root `index.html` and breaks from `/capacity`, where it would resolve to `/capacity/data/prison-capacity.json`. Change it to the absolute `/data/prison-capacity.json`.

Better still, use the pipeline that already exists. Put the file at `data/processed/prison-capacity.json` in the repository, let `stage-data.mjs` copy it into `site/public/data/` on build as it does for every other derived table, and update `OUT_PATH` in the ingest script to write there. That removes the parallel data path entirely and means the capacity figures follow the same route as the rest of the site's data.

## The ingest, which should follow your existing pattern

Do not add the kit's `.github/workflows/prison-figures.yml` as a second parallel workflow. The repository already has `.github/workflows/etl-refresh.yml` with a `workflow_dispatch` trigger and an `etl/fetch.py` that supports `--dry-run`. Fold the prison bulletin ingest into that pattern: move the logic from `scripts/fetch_prison_figures.py` into the `etl/` package in the house style, and add it to the existing workflow, or add a sibling workflow that matches the existing one's conventions if the schedules genuinely need to differ. The bulletin publishes on Mondays, so a Tuesday run is the requirement, not the specific file.

Everything in Step 3 about the parser still stands: match row labels rather than cell coordinates, keep the sanity check on the plausible range, keep the previous values on a failed parse rather than writing nulls, and commit the sheet dump so the labels can be corrected from it.

## Egress

Three separate environments have now failed to reach `gov.uk`, including yours. Treat the GitHub Actions runner as the only place the ingest will actually run, and use `workflow_dispatch` for the first parse confirmation exactly as the existing ETL workflow does. Report what the dump contains before anything is committed to the data directory.
