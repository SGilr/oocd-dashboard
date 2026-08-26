# Methodology and Limitations

This is the canonical version. The methodology page on the site renders from
this file, so the two cannot drift apart. Sections marked with an injection
comment are filled in at build time from the manifest, from
`etl/annotations.yml` and from the derived tables, so the figures quoted on the
site are the figures that were built rather than figures typed in by hand.

## What this dashboard is

It shows how the 43 territorial police forces of England and Wales, and British
Transport Police, distribute their recorded crime outcomes, and how much of that
distribution runs through out of court routes. It shows volume, share, mix and
change over time, force by force.

## What this dashboard is not

It is not an assessment of whether those decisions were right, consistent,
proportionate or effective. No published national dataset supports that claim.
The section headed "What this dashboard cannot tell you" sets out what is
missing and why it cannot be worked around with the data that exists.

There is no composite score anywhere on the site and no overall league position.
A rank exists only inside a stated measure, in a stated year, on a stated count
basis, with the notes that apply to each force visible beside it.

## Source

One source, used throughout.

Home Office (2026) *Police recorded crime and outcomes open data tables*.
London: Home Office. Available at:
https://www.gov.uk/government/statistical-data-sets/police-recorded-crime-and-outcomes-open-data-tables

The data is Crown copyright, reused under the Open Government Licence v3.0. The
required attribution statement is in `DATA-LICENCE.md` and in the footer of every
page.

Two series are used. The outcomes open data tables, one file per financial year
from 2014/15, give the outcome counts. They are titled by the year the financial
year ends in, so "Outcomes open data, year ending March 2026" is financial year
2025/26. The archive covering the years ending March 2006 to March 2014 is
published as an ODS file and falls wholly before the period covered here, so it
is not downloaded. The police force area crime tables give
recorded crime, which is the denominator for the rate measure.

<!-- INJECT:MANIFEST -->

Every derived figure is traceable to a file in `data/manifest.json`, which
records the resolved URL, the retrieval timestamp in Coordinated Universal Time,
the file size and the SHA256 checksum of the file as downloaded. The raw files
are not committed. They are rebuilt from the manifest, and the checksums confirm
that a rebuild produced the same bytes.

## Definitions

### Outcome types

The published tables carry an outcome type code from 1 to 22. Six of them are
out of court disposals.

<!-- INJECT:OUTCOME-TYPES -->

Outcome type 0, not yet assigned an outcome, is not an outcome at all. It counts
offences still waiting for one, and it appears in the published tables as a row
like any other. It is excluded from every figure here, including from all
assigned outcomes. In the year ending March 2026 it covered 384,808 offences on
the recorded basis, so including it would have inflated that denominator by
about 8 per cent. It carries no counts on the closed basis, which is a further
reason to prefer that basis.

Outcome type 19, National Fraud Intelligence Bureau fraud case, does not appear
in the year ending March 2026 file at all. A type can be legitimately absent
from a year, so a missing one is reported for review rather than failing the
build, except for the seven types the classification depends on.

Outcome type 4, taken into consideration, is not an out of court disposal. It
records an offence the person admitted and asked the court to take into account
alongside the offences being prosecuted, so it accompanies a prosecution rather
than replacing one. It is excluded throughout. Sweeping it in would inflate every
out of court figure on the site.

### Positive outcomes

A positive outcome is one where somebody was held to account: outcome type 1,
charge or summons, plus the six out of court types. Everything else, including
cases closed with no suspect identified and cases closed because the victim did
not support action, is not a positive outcome.

### All assigned outcomes

Every outcome the force recorded against a closed investigation or a recorded
offence, whichever count basis is selected. This is the widest denominator on
the site.

## The count basis

The published tables carry two count columns and they are not interchangeable.

**Outcomes for investigations that were closed in the quarter** counts the
outcome in the quarter the investigation ended. This is the default on the site.
It describes decision behaviour: it answers what the force decided in a period,
regardless of when the offence was recorded.

**Outcomes for offences that were recorded in the quarter** counts the outcome
against the quarter the offence was recorded. It undercounts recent quarters,
because investigations into recently recorded offences are still open and have
not yet been assigned an outcome. A trend built on this basis falls away at the
right hand end for a reason that has nothing to do with decision making.

Both bases are carried through every derived table and every download. The basis
on screen is named on every page, and the compare page lets you switch between
them.

## The denominators

Three denominators are defensible and they answer different questions, so all
three are offered.

**Share of positive outcomes.** Out of court disposals divided by charge or
summons plus all six out of court types. Of the cases where somebody was held to
account, how many were dealt with outside court. This is the default, because it
comes closest to the decision under examination.

**Share of all assigned outcomes.** Out of court disposals divided by every
assigned outcome. How much of everything the force closes runs out of court.
This number is lower and moves with the proportion of cases closed with no
suspect identified, which is largely a function of offence mix.

**Rate per 1,000 recorded crimes.** Out of court disposals divided by recorded
crime in the force area, multiplied by a thousand. Volume normalised for force
size.

When a subset of the six disposal types is selected, the numerator narrows and
the denominator does not. The share for each type therefore adds up to the share
for all six together. Narrowing the denominator with the numerator would make
every subset look larger than it is.

### Population and per capita measures

There is no per capita measure on this dashboard.

Mid year population estimates per police force area could not be retrieved from
a named published source when these tables were built, so the measure is omitted
rather than estimated. `data/processed/denominators.json` records the omission
and the reason in its metadata. If a verified source is added later, the measure
can be restored without changing any other part of the pipeline.

### Forces excluded from size adjusted measures

British Transport Police polices the railway network rather than a geographical
area with residents. It has no resident population and a distinct offence
profile, so it is excluded by default from the rate measure. It remains in the
share measures, where the denominator is the force's own outcomes.

## Fraud

Fraud reported to Action Fraud, Cifas and Financial Fraud UK is recorded
centrally rather than by police forces.

The consequence for the outcomes tables is stronger than expected. In the year
ending March 2026 the only fraud offence group present is "Fraud offences to
2012/13", every code in it is expired, and it carries no counts. The outcomes
tables therefore contain effectively no fraud, and excluding fraud changes
nothing in any measure built on them: the all fraud and the exclude fraud totals
for that year are identical to the unit.

The exclude fraud control is kept so that this can be seen rather than assumed,
and because fraud does affect the police force area crime tables, which supply
the denominator for the rate per 1,000 recorded crimes. It matters for that
measure and not for the share measures.

Rows attributed to Action Fraud, Cifas and Financial Fraud UK as if they were
forces are dropped at extract time and counted in `coverage.json`, so they are
never treated as a forty fifth force. None appeared in the year ending March
2026 outcomes file, which lists exactly 44 forces.

## Notes on the series

Each note below is held in `etl/annotations.yml`. Adding one is a change to that
file alone: it appears as a numbered footnote marker on every chart it touches
and in full here. The numbering is stable across the site.

<!-- INJECT:ANNOTATIONS -->

## What this dashboard cannot tell you

This section is the point of the dashboard as much as the charts are.

**Nothing about conditions.** There is no national record of what condition was
attached to a disposal. A conditional caution with a rehabilitative requirement
and one with no requirement at all are the same row in this data.

**Nothing about engagement or completion.** There is no national record of
whether the person turned up, took part, or finished. A diversionary activity
that was completed and one that was abandoned in the first week are
indistinguishable here.

**Nothing about consistency or proportionality.** The data carries no
information about the seriousness of the individual offence beyond its offence
code, nothing about the person's history, and nothing about the reasoning behind
the decision. Two forces with the same share may be making very different
decisions on very similar cases, and this data cannot separate those.

**Not every disposal reaches the Police National Computer.** Recording practice
varies, and informal disposals in particular are not reliably held on the Police
National Computer. A disposal counted here may leave no trace in the record that
a later decision maker sees.

**No published outcome measure per force.** Ministry of Justice proven
reoffending statistics are built from court disposals and cautions, and exclude
the out of court disposals that are not cautions. There is therefore no published
reoffending measure that covers the disposals shown here, and no way to attach an
effectiveness figure to a force from published data.

**Recorded crime is not crime.** The denominator for the rate measure is
recorded crime, which reflects reporting and recording practice as well as
offending. Changes in recording practice move the denominator without anything
happening in the world.

**Comparison across the series is comparison across changing definitions.**
Offence codes are added and retired. Outcome 22 changed from voluntary to
compulsory recording. Some forces have withdrawn disposal types by policy. Each
of these is noted above, and each of them means a line on a chart can move for
reasons that have nothing to do with decision making.

Anything that would imply effectiveness, quality or consistency of decision
making is not on this site and should not be derived from it.

## Validation

The build fails rather than shipping a wrong chart. `etl/validate.py` runs after
every extract and its report is written to `data/validation-report.json`. The
checks are:

- All 44 forces are present, and any force name in the source files that does not
  match the canonical list is reported rather than dropped in silence.
- Every outcome type from 1 to 22 appears in at least one financial year.
- No count that feeds a derived total is negative. A negative inside outcome type
  0 is recorded as a note instead: a force can reclassify more offences in a
  quarter than it records, which produces a small negative there, and that row
  never enters a total. Humberside does this four times in the year ending March
  2026, on distraction burglary.
- No key of force, financial year, quarter, offence code and outcome type repeats
  in a source file, which would double count.
- No derived table has more than one row for a key.
- The derived out of court total equals the sum of its six components, the
  positive total equals charge plus those six, positive outcomes do not exceed
  all assigned outcomes, and excluding fraud never produces a larger total than
  including it.
- A movement of more than 40 per cent in a force series between consecutive years
  is flagged for a person to look at. It does not fail the build, because outcome
  22 becoming compulsory moved some forces by more than that, correctly.
- At least one national headline figure reconciles with the figure published in
  the corresponding Home Office bulletin, within a stated tolerance. The targets
  are held in `etl/reconciliation.yml`, typed in by a person who has read the
  bulletin, so the check compares the extract with something external rather than
  with itself.

<!-- INJECT:VALIDATION -->

## Rebuilding this from scratch

```
git clone <repository>
cd oocd-dashboard

# Python 3.11
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"

# Extract, transform, validate. The first step reads gov.uk.
.venv/bin/python etl/fetch.py --dry-run     # check what was discovered
.venv/bin/python etl/fetch.py
.venv/bin/python etl/transform.py
.venv/bin/python etl/validate.py --check-urls

# Site
cd site && npm ci && npm run build
```

Running the extract without network access to gov.uk is not possible. To work on
the site without it, build against the synthetic fixtures:

```
.venv/bin/python etl/make_fixtures.py
.venv/bin/python etl/transform.py --data-root fixture
.venv/bin/python etl/validate.py --data-root fixture
cd site && npm run build
```

A build made from fixtures carries provenance `fixture`, and every page shows a
banner saying the figures are invented. It must not be published.

## References

British Transport Police (2026) *About us*. London: British Transport Police.

Home Office (2026) *Police recorded crime and outcomes open data tables*.
London: Home Office.

Home Office (2026) *Police recorded crime and outcomes open data tables user
guide*. London: Home Office.

Ministry of Justice (2026) *Proven reoffending statistics: definitions and
measurement*. London: Ministry of Justice.

Office of the Police and Crime Commissioner for West Yorkshire (2024) *Out of
court disposals*. Wakefield: West Yorkshire Police and Crime Commissioner.

The source URL for each note is listed with the note, and its verification state
is shown beside it.
