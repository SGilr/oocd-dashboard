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

Two series are used.

The outcomes open data tables, one xlsx file per financial year from 2014/15,
give the outcome counts. They are titled by the year the financial year ends in,
so "Outcomes open data, year ending March 2026" is financial year 2025/26. The
archive covering the years ending March 2006 to March 2014 falls wholly before
the period covered here, so it is not downloaded.

The police recorded crime open data police force area tables give recorded
crime, which is the denominator for the rate measure. They are published as ODS,
and the current file covers the year ending March 2013 onwards in one file
rather than one file per year. Two older archives, covering March 2003 to March
2007 and March 2008 to March 2012, fall before the period covered here and are
not downloaded. A file of police recorded crime subcodes for selected violence
against women and girls offences is also published on the same page. Nothing on
this dashboard uses it, so it is not downloaded.

ODS files are read by streaming the XML out of the zip rather than loading the
document. The force area file is 14.2 MB compressed and its `content.xml`
expands to 359 MB, so loading it was never an option. It holds one sheet per
financial year, fourteen of them from 2012/13 to 2025/26, plus a cover sheet and
a notes sheet which are skipped. Each sheet gets its own header detection rather
than the first sheet's column order being assumed for the rest.

Two things about that file bear on the measures. Action Fraud appears in it as
though it were a police force, with its own offence code, in the years to
2014/15; those rows are dropped, because it is not a force. And British
Transport Police leaves the table after 2014/15, so from then on it has no
recorded crime figure at all. That is the second reason it is excluded from the
rate measure, alongside having no resident population. The police force area crime tables give
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
in the year ending March 2026 file at all. The bulletin explains why: it applies
only to fraud recorded by that bureau, which is reported separately, and the
fraud chapter was dropped from the year ending March 2026 publication because
Report Fraud replaced the bureau and legacy Action Fraud on 4 December 2025. A
type can be legitimately absent from a year, so a missing one is reported for
review rather than failing the build, except for the seven types the
classification depends on.

Outcome types 1a, 2a and 3a appear in the published grouping but not in the year
ending March 2026 file. They are "of which" rows: the subset of outcomes 1, 2
and 3 where the outcome relates to an offence other than the one recorded. They
sit inside their parent type, so adding them would double count. The extract
drops them and records the number dropped in `coverage.json`. They are not a
split between simple and conditional cautions, which the published tables do not
support at all.

Outcome type 4, taken into consideration, is not an out of court disposal. It
records an offence the person admitted and asked the court to take into account
alongside the offences being prosecuted, so it accompanies a prosecution rather
than replacing one. It is excluded throughout. Sweeping it in would inflate every
out of court figure on the site.

### The Home Office's own grouping

The published tables carry an outcome group column, which is the Home Office's
own classification rather than ours, and the bulletin sets the same grouping out
in its Table 1.1. For the year ending March 2026 it groups the outcome types
like this, and the grouping matches the classification used here exactly:

| Outcome group | Outcome types | Recorded basis |
| --- | --- | --- |
| Out-of-court (formal) | 2, 3, 6 | 42,474 |
| Out-of-court (informal) | 7, 8 | 174,735 |
| Diversionary, educational or intervention activity | 22 | 23,277 |
| **The six types counted here** | **2, 3, 6, 7, 8, 22** | **240,486** |
| Taken into consideration | 4 | 3,410 |

Taken into consideration is a group of its own, separate from both out of court
groups, which is independent confirmation that excluding outcome type 4 from the
out of court set is the right reading and not a judgement of ours.

Note that the Home Office reports outcome 22 separately from both out of court
groups, whereas this dashboard counts it as the sixth out of court disposal
type. That is a deliberate difference, and it is why a published out of court
figure will be smaller than the figure here unless outcome 22 is added to it.
The reconciliation targets name the outcome types they cover so the two can be
compared without confusion.

### Coverage differs between published tables

Figures here cover all 44 forces in every year, because the open data tables
carry all 44. The bulletin is not consistent on this: different tables in it
cover 44 forces, 43 including British Transport Police, or 43 excluding it, and
several exclude Humberside or Greater Manchester where record level data was not
supplied in time. A figure quoted from the bulletin will therefore not always
match the same figure here, and the reason is coverage rather than arithmetic.

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
- At least one national headline figure reconciles with a figure published in a
  Home Office bulletin, within a stated tolerance. The targets are held in
  `etl/reconciliation.yml` and come in two kinds. A target of kind `published`
  is read from a bulletin by a person, and is the only kind that can catch a
  misreading of what the data means, because it comes from outside the open data
  tables. A target of kind `recomputation` is the same source computed by a
  different route, such as a pivot table built by hand, which catches
  implementation error but shares any misunderstanding with the extract. A build
  on live data fails without at least one target of the first kind.

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
