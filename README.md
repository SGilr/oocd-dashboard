# Out of Court Disposals Dashboard

A public, static, reproducible dashboard of out of court disposals by police
force in England and Wales, built for a symposium convened with De Montfort
University and the East Midlands Policing Academic Collaboration, and produced by
Oxon Advisory.

## What it is

It shows how the 43 territorial police forces of England and Wales, and British
Transport Police, distribute their recorded crime outcomes, and how much of that
distribution runs through out of court routes. It shows volume, share, mix and
change over time, force by force.

## What it is not

It is not an assessment of whether those decisions were right, consistent,
proportionate or effective. No published national dataset supports that claim.
There is no national record of what condition was attached to a disposal, whether
the person engaged with it or whether they completed it, and Ministry of Justice
proven reoffending statistics exclude the out of court disposals that are not
cautions, so there is no published outcome measure per force.

The limitation is built into the site as a section of its own rather than as a
disclaimer at the bottom. There is no composite score anywhere and no overall
league position. A rank exists only inside a stated measure, in a stated year, on
a stated count basis, with the notes that apply to each force visible beside it.

## Data source

Home Office, police recorded crime and outcomes open data tables:
https://www.gov.uk/government/statistical-data-sets/police-recorded-crime-and-outcomes-open-data-tables

Crown copyright, reused under the Open Government Licence v3.0. See
`DATA-LICENCE.md` for the required attribution statement. The code is MIT
licensed, see `LICENSE`.

Two series are used: the outcomes open data tables, one file per financial year
from 2014/15, and the police force area crime tables, which give the recorded
crime denominator.

## The measurement decisions

These are the choices that make the difference between a chart and a wrong chart.
`docs/METHODOLOGY.md` is the full version.

**Which count column.** The published tables carry two, and they are not
interchangeable. Outcomes attributed to offences recorded in the quarter
undercount recent quarters, because those investigations are still open. Outcomes
for investigations closed in the quarter is the better basis for describing
decision behaviour, so it is the default. Both are carried through every derived
table and the basis on screen is named on every page.

**Which denominator.** Three are defensible and they answer different questions:
share of all assigned outcomes, share of positive outcomes, and rate per 1,000
recorded crimes. All three are offered. The default is share of positive
outcomes, which comes closest to the decision under examination.

**Which outcome types.** Out of court disposals are outcome types 2 and 3
(cautions, youths and adults), 6 (penalty notices for disorder), 7 (cannabis or
khat warning), 8 (community resolution) and 22 (diversionary, educational or
intervention activity). Outcome 4, taken into consideration, is not an out of
court disposal and is excluded. Outcome 1, charge or summons, is the comparator.

**No per capita measure.** Mid year population estimates per police force area
could not be retrieved from a named published source, so the measure is omitted
rather than estimated.

## Discontinuities handled in code

These live in `etl/annotations.yml`, which is the single source of truth for
caveats. Adding one is a change to that file alone: it appears as a numbered
footnote marker on every chart it touches and in full on the methodology page.

1. Outcome 22 was recorded voluntarily from April 2019 and became compulsory from
   April 2021. Charts shade the period before 2021/22.
2. Some forces restrict which disposals they use as a matter of policy, so a fall
   in a series can be a policy decision rather than a change in behaviour.
3. Fraud recorded centrally by Action Fraud, Cifas and Financial Fraud UK is
   attributed to force areas and distorts offence mix. Every measure has an
   exclude fraud control.
4. British Transport Police has no resident population, so it is excluded by
   default from measures that normalise for force size.
5. Offence codes expire during the period. The extract reads the published
   expired flag rather than assuming a stable code list.

## Layout

```
etl/            fetch.py, transform.py, validate.py, make_fixtures.py,
                annotations.yml, reconciliation.yml, tests/
data/
  raw/          gitignored, rebuilt from the manifest
  manifest.json source URLs, retrieval timestamps, SHA256 checksums
  processed/    committed JSON and CSV
  fixture/      gitignored in full, synthetic data for offline work
site/           Astro project
docs/           METHODOLOGY.md, DEPLOYMENT.md
.github/workflows/  etl-refresh.yml, ci.yml
```

## Rebuilding from scratch

```bash
# Python 3.11
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"

.venv/bin/python -m pytest etl/tests -q

# Extract. The first command reads gov.uk and downloads nothing.
.venv/bin/python etl/fetch.py --dry-run
.venv/bin/python etl/fetch.py
.venv/bin/python etl/transform.py
.venv/bin/python etl/validate.py --check-urls

# Site
cd site
npm ci
npm run build      # output in site/dist
```

`etl/validate.py` gates the build. It exits non zero when the force count is
wrong, an outcome type is missing from every year, a count is negative, a key
repeats, a derived total does not reconcile with its components, an annotation
source URL does not resolve, or a national headline figure does not match the
published bulletin within tolerance. A movement over 40 per cent in a force
series is flagged for a person to read rather than failing, because outcome 22
becoming compulsory moved some forces by more than that, correctly.

### Working without network access to gov.uk

`etl/make_fixtures.py` generates synthetic raw files with the same shape as the
published ones, so the whole pipeline and the whole site can be exercised
offline.

```bash
.venv/bin/python etl/make_fixtures.py
.venv/bin/python etl/transform.py --data-root fixture
.venv/bin/python etl/validate.py --data-root fixture
cd site && npm run build
```

The numbers are invented. The fixture tree is gitignored in full, so they cannot
reach `data/processed/`, the manifest records provenance `fixture`, validation
flags it, and the site puts a red banner on every page. A fixture build must not
be published.

## Deployment

Cloudflare Pages, git integration, static output. `docs/DEPLOYMENT.md` has the
build settings, the environment variable, the headers, the analytics choice and
the four things to confirm before the first production deploy.

## If this directory sits inside a larger repository

The project is self contained and is meant to be its own repository. To split it
out, keeping its history:

```bash
git subtree split --prefix=oocd-dashboard -b oocd-dashboard-only
# then push that branch to the new repository's default branch
```

Or copy the directory into a fresh repository if the history does not matter.
Until it is its own repository, the workflows in `.github/workflows/` will not
run, because GitHub only reads that path at the repository root, and Cloudflare
Pages needs the root directory setting adjusted to match.

## Credits

Produced by Oxon Advisory. Built for a symposium convened with De Montfort
University and the East Midlands Policing Academic Collaboration.

Contains public sector information licensed under the Open Government Licence
v3.0. Source: Home Office, police recorded crime and outcomes open data tables.
The Home Office has not reviewed, approved or endorsed this dashboard or any
measure on it.
