# Prison demand page for oocd.howpreventionworks.com

A single static page with a live capacity panel, a demand cascade, a reverse-solve
model and an evidence section. No build step, no dependencies, no framework.

## What is here

```
capacity.md                         the work order: hand this to Claude Code
index.html                          the page, self-contained apart from Google Fonts
data/prison-capacity.json           the figures the capacity panel reads
scripts/fetch_prison_figures.py     weekly ingest, standard library only
.github/workflows/prison-figures.yml  runs the ingest on Tuesdays and commits the result
_headers                            Cloudflare Pages cache rules for the data path
```

Start with `capacity.md`. It carries the deployment steps, the standing constraints,
the verification checklist and the one open item, and is written to be handed to an
agent working in the repository.

## Deploying

Drop the four files into the repository behind the subdomain and publish. On
Cloudflare Pages the build command is empty and the output directory is the repository
root. The page fetches `data/prison-capacity.json` at a relative path, so it works from
any directory as long as `data/` sits beside `index.html`. If the fetch fails the panel
falls back to figures hard-coded in the script and says so.

## The weekly ingest, and the one thing it needs from you

The Ministry of Justice publishes the weekly estate bulletin as an `.ods` file every
Monday. The GOV.UK Content API exposes the newest attachment as JSON, so the script
finds the file without scraping HTML, downloads it, unzips it and reads `content.xml`
directly.

It locates the population and capacity figures by matching row labels rather than cell
coordinates, so a layout change does not silently produce a wrong number.

**The label patterns are candidates, not confirmed.** The bulletin could not be opened
from the environment this was written in, because `assets.publishing.service.gov.uk`
was unreachable there. So the first run does two things: it writes the whole flattened
sheet to `data/_sheet-dump.json`, and if it cannot match both figures it keeps the
previous values, marks `parser_status` as `needs_review` and exits non-zero. The page
then displays the last verified figures and says the ingest needs attention rather than
showing nothing or showing nulls.

To close that loop:

```bash
python3 scripts/fetch_prison_figures.py --dry-run
```

Read what it prints. If both figures came back sensible, you are done. If not, open
`data/_sheet-dump.json`, find the real row labels, and add them to the `LABELS`
dictionary at the top of the script.

Enable the workflow in the Actions tab. It needs `contents: write`, which is declared
in the workflow file, and no secrets.

## The design rule the page runs on

Ink means measured, rust means modelled. Every figure set in ink comes from a published
source named in the notes. Every figure set in rust is produced by the calculator from
parameters the reader has set. This is deliberate: a health warning in a banner gets
separated from the number it qualifies as soon as anyone screenshots the number, and a
warning carried in the colour system travels with it.

Two consequences worth keeping if the page is edited later. The calculator will not
produce a forward estimate, only a required volume for a target the reader chooses,
because a forward number can be quoted as a forecast and a required volume cannot. And
there is no ticking savings counter, because the cost per place is not cash-realisable
at the margin.

## Palette

Validated against the colourblind-safety and contrast checks in both themes.

| Role | Light | Dark |
|---|---|---|
| Resolved out of court | `#12906a` | `#199e70` |
| Prosecuted and imprisoned | `#2a78d6` | `#3987e5` |
| Modelled | `#b4441b` | `#e0693a` |
| Surface | `#f6f3ec` | `#16150f` |

Worst all-pairs separation is Delta E 9.1 light and 8.5 dark under simulated
protanopia and deuteranopia, against a target of 8, with every mark clearing 3:1
against its surface. If you change a hue, re-run the check before publishing.

## Figures to confirm before this goes public

The year ending December 2025 sentencing figures (1.20 million sentenced, 77% fines,
88,100 immediate custody, 58% under twelve months, 33.5% indictable custody rate) were
read from the GOV.UK bulletin page rather than from the outcome tables. Confirm them
against the published tables. The recorded crime total of about 5.27 million is a sum
of the victim-based and non-victim-based figures and is shown as approximate for that
reason.
