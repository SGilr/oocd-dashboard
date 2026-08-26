# Data Licence

The code in this repository is licensed under the MIT Licence, in `LICENSE`.
The data is not. This file records the terms that apply to the data.

## Source data

The underlying statistics are Crown copyright. They are published by the Home
Office as the police recorded crime and outcomes open data tables, and are
reused here under the Open Government Licence v3.0.

Landing page:
https://www.gov.uk/government/statistical-data-sets/police-recorded-crime-and-outcomes-open-data-tables

Licence text:
https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

## Required attribution statement

Any reuse of the data in this repository, or of the derived tables in
`data/processed/`, must carry the following statement:

> Contains public sector information licensed under the Open Government
> Licence v3.0. Source: Home Office, police recorded crime and outcomes open
> data tables.

## Derived tables

The files in `data/processed/` are derived from the source data by the scripts
in `etl/`. They remain subject to the Open Government Licence v3.0. The
classification and aggregation logic that produced them is documented in
`docs/METHODOLOGY.md` and is MIT licensed as code.

Every derived file is traceable to a source file recorded in
`data/manifest.json`, with the resolved URL, the retrieval timestamp and the
SHA256 checksum of the file as downloaded.

## What the Open Government Licence does not cover

The Open Government Licence does not transfer any endorsement. The Home Office
has not reviewed, approved or endorsed this dashboard, its derived measures or
its commentary. Errors in the derived tables are the responsibility of Oxon
Advisory, not of the Home Office.
