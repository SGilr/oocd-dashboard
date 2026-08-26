# Handover

Written 26 August 2026, at the end of the build. For whoever picks this up
next, including its author in six months.

## What this is

A public dashboard of out of court resolutions by police force in England and
Wales, live at https://oocd.howpreventionworks.com, built for a symposium
convened with De Montfort University and the East Midlands Policing Academic
Collaboration.

It shows volume, share, mix and change over time for the 43 territorial forces
and British Transport Police, from 2014/15 to 2025/26, from one source.

It says nothing about whether those decisions were right, consistent,
proportionate or effective. No published national dataset supports that claim.
The methodology page has a section headed "What this dashboard cannot tell you"
and it is the most important page on the site. Anyone tempted to add a measure
of effectiveness should read it first.

## Where everything is

| Thing | Where |
| --- | --- |
| Live site | https://oocd.howpreventionworks.com |
| Repository | https://github.com/SGilr/oocd-dashboard |
| Hosting | Cloudflare Workers, static assets only, config in `wrangler.jsonc` |
| Source data | Home Office police recorded crime and outcomes open data tables |
| Canonical methodology | `docs/METHODOLOGY.md`, which the site renders |
| Caveats | `etl/annotations.yml`, the single source of truth |
| Deployment notes | `docs/DEPLOYMENT.md` |

## Changing something

The site rebuilds and deploys on every push to `main`. There is no separate
deploy step.

```bash
git clone https://github.com/SGilr/oocd-dashboard.git
cd oocd-dashboard

# Python, for the extract
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest etl/tests -q          # 143 tests

# Site
cd site && npm ci && npm run build               # output in site/dist
npm run a11y                                      # axe, exits non zero on any violation
```

To work on the site without re-downloading 460 MB of spreadsheets, build
against the synthetic fixtures:

```bash
.venv/bin/python etl/make_fixtures.py
.venv/bin/python etl/transform.py --data-root fixture
cd site && OOCD_DATA_ROOT=../data/fixture npm run build
```

A fixture build puts a red banner on every page saying the figures are
invented, and the fixture tree is gitignored in full, so invented numbers
cannot reach `data/processed/`. Never publish one.

## How the pipeline works

`etl/fetch.py` reads the gov.uk landing page, resolves the current asset URLs,
downloads the twelve outcomes files and one police force area file, and writes
`data/manifest.json` with the URL, timestamp, size and SHA256 of each. Raw
files are not committed. They are rebuilt from the manifest.

`etl/transform.py` streams those files and writes the derived tables to
`data/processed/`, as JSON for the site and CSV for people. Both are committed.

`etl/validate.py` checks the result and exits non zero if it is wrong, which
stops the build.

Run `etl/fetch.py --dry-run` before anything else. It downloads nothing and
prints what it found on the landing page and what it passed over and why. If
the Home Office changes the page, that output is where you will see it.

Run `etl/transform.py --survey` when a new year is published. It reads every
file once and reports every value the ETL has to interpret: the sheets in each
workbook, every non-numeric value in the count columns and whether it is
handled, the expired flag values, the outcome type values, unmatched force
names, and the headers wherever they differ between years. One pass finds every
surprise. Fixing them one crash at a time costs a ten minute run per fix.

## The decisions that shape every figure

Four choices determine what the numbers mean. All are argued in
`docs/METHODOLOGY.md` and all are visible on the site.

**The count basis.** The published tables carry two count columns and they are
not interchangeable. Outcomes for offences recorded in the quarter undercount
recent quarters, because those investigations are still open. Outcomes for
investigations closed in the quarter is the default here, because it describes
decision behaviour. Both are carried through every table.

**The denominator.** Three are defensible and answer different questions:
share of positive outcomes, share of all assigned outcomes, and rate per 1,000
recorded crimes. All three are offered. The default is share of positive
outcomes, which comes closest to the decision under examination.

**The outcome types.** Out of court resolutions are types 2, 3, 6, 7, 8 and 22.
Outcome 4, taken into consideration, is excluded: it accompanies a prosecution
rather than replacing one. The Home Office's own outcome group column agrees,
grouping type 4 separately from both out of court groups. That agreement is
worth knowing about, because it means the classification is not a judgement of
ours.

**No composite score.** There is no overall ranking anywhere and there must not
be one. A rank exists only inside a stated measure, in a stated year, on a
stated count basis, with the notes that apply to each force beside it.

## What the data will do to you

Every item here was found by running real code against real published files.
None of them announce themselves, and each would have produced a confident
wrong answer. All are now pinned by a test.

**Outcome type 0 is not an outcome.** "Not yet assigned an outcome" is a row
like any other in the published files. Leaving it in "all assigned outcomes"
puts undecided cases into the denominator of a measure about decisions, and
inflated it by 384,808 offences, about 8 per cent. It is excluded everywhere.

**Zero is falsy.** `str(cell or "")` turns an integer 0 into an empty string,
which made all 32,384 rows of outcome type 0 disappear without a word. Use
`text_of()` from `etl/common.py`. There is a test class named after this.

**Not applicable comes in five spellings.** `NA`, `N/A`, `N/A - Offence code
expired`, `N/A - offence code expired` and `N/A - data not provided`, and which
one appears varies by year. `to_int()` handles the family. Anything it does not
recognise raises rather than becoming a zero.

**"Data not provided" is not zero.** It means the force did not supply the
count, so that force year is understated rather than genuinely low. Eight
forces in 2014/15. It reads as zero for the arithmetic but every affected force
and year is named in the validation report and on the force's own page.

**Greater Manchester 2019/20 is missing data with no marker.** The force could
not supply data from July 2019 after a records system change, and those
quarters simply carry almost nothing. Disposals fall from 8,376 to 2,107 and
recover to 7,435. Nothing in the file signals it. It has its own annotation
because anyone reading that chart without one concludes the opposite of the
truth.

**The expired offence code flag is a lower case `x`,** not "Yes". Reading it as
false made every retired code look current.

**Negative counts are corrections, not corruption.** A force that cancels or
reclassifies a crime recorded earlier produces a negative adjustment and the
Home Office publishes it. 798 rows in types that feed the figures. They are
carried exactly as published, because rewriting them to zero would stop the
totals reconciling with the bulletin. A quarterly cell can therefore be
negative. An annual total cannot, and the build stops if one is.

**The landing page lists far more than the two series used here.** Firearms and
knives subsets, three subcode files, supplementary metrics, a geographical
reference table, and an "Outcomes for alternate offences" file. That last one
holds outcome types 1a, 2a and 3a, which are subsets already inside outcomes 1,
2 and 3. Taking it would double count every charge and caution. Classification
is by link title, never by the heading above it, because everything on that
page sits under the same headings.

**Simple and conditional cautions cannot be separated.** Types 2 and 3 cover
both and nothing in the published tables distinguishes them. A force that has
withdrawn simple cautions by policy still shows a large caution count. Any
reading of these series as evidence about simple cautions specifically is
unsupported. This killed a claim that was in the original brief.

**Fraud is effectively absent from the outcomes tables.** The only fraud group
is "Fraud offences to 2012/13", wholly expired, carrying no counts. The exclude
fraud control changes nothing in any share measure, and is kept so that can be
seen rather than assumed. It does matter for the rate measure, because fraud is
in the recorded crime denominator.

**British Transport Police has no denominator after 2014/15.** It leaves the
force area crime tables, so the rate measure shows "not available" rather than
a zero or an invented figure.

## What must stay true

**Reconciliation.** `etl/reconciliation.yml` holds figures the derived tables
are checked against. A target of kind `published` comes from a Home Office
bulletin and is the only kind that can catch a misreading of what the data
means. A build on live data fails without at least one. Do not add a target
computed from the same open data tables and call it published: that compares
the extract with itself and always passes.

**Loud failure.** The ETL fails on an unmapped column header, an unrecognised
count value, an unmatched force name, or a missing essential outcome type. That
is deliberate. Every silent drop found during the build produced a wrong answer
that looked right. If you are tempted to add a `try: except: pass`, do not.

**Annotations are data.** Adding a caveat is a change to `etl/annotations.yml`
alone. It appears as a numbered footnote on the charts it affects and in full
on the methodology page. Only notes marked `chart_marker: true` get a marker,
because most notes are national and nine identical markers on every chart tell
a reader nothing.

**Sources are verified.** Every annotation carries a source URL and a
verification state. `python etl/validate.py --urls-only` resolves them from a
machine with network access. A 404 or 410 fails the build. A 403, 429 or
timeout leaves the existing state alone, because "I could not reach it" is not
"it is gone". British Transport Police answers 403 to a script and 200 to a
browser, and is verified by a person. That is expected, not a regression.

**Themes agree.** `site/scripts/check-theme-tokens.mjs` runs before every build
and fails if a colour token is defined in one dark scope and not the other.
This is not theoretical: the interquartile band was light on dark for anyone
who chose dark deliberately, and both scopes were valid CSS on their own.

**Accessibility.** `npm run a11y` runs axe against every page type in both
themes and exits non zero on any violation. It was clean at handover. WCAG 2.1
AA is a requirement of this dashboard, not an aspiration.

## The quarterly refresh

`.github/workflows/etl-refresh.yml` runs at 07:15 on the 5th of February, May,
August and November, a fortnight after the usual release. It reruns fetch,
transform and validate, and opens a pull request when the derived tables
change, with the validation report and a diff summary in the body. It never
pushes to `main`.

Review the manifest first. A changed URL or checksum with unchanged figures
means the Home Office republished a file, and that is worth understanding
before merging.

It needs two repository settings, under Settings, Actions, General, Workflow
permissions: read and write permissions, and permission for Actions to create
pull requests. Without both it does the work and fails at the last step.

You can run it by hand from the Actions tab. It was tested that way on
26 August 2026 and correctly opened nothing, the tables being unchanged.

## Outstanding

Nothing blocking. Two tidy ups:

The four GitHub Actions in the workflows target Node 20 and are being forced
onto Node 24. A warning, not a failure. Bump `actions/checkout`,
`actions/setup-python`, `actions/upload-artifact` and
`peter-evans/create-pull-request` to their current majors when convenient.

Bot protection on the Cloudflare zone refuses a request from a script while
allowing the same request from a browser, so `curl` on the site gets a 403.
That is why the data page points at the repository's raw URLs for machine
readable access. The zone setting was left alone deliberately, because other
subdomains may need it. If the zone ever moves to a paid plan, a WAF rule
skipping Super Bot Fight Mode for this hostname would let the site serve
scripts directly.

## Ask before

Substituting a data source. Dropping a force or a year for any reason.
Publishing a figure that cannot be traced to a file in the manifest. Adding any
measure that implies effectiveness, quality or consistency of decision making.
That last one is not supported by this data and must not appear on the site.

## Credit and licence

Produced by Oxon Advisory. The code is MIT licensed. The data is Crown
copyright, reused under the Open Government Licence v3.0, and any reuse must
carry the attribution statement in `DATA-LICENCE.md`. The Home Office has not
reviewed, approved or endorsed this dashboard or any measure on it.
