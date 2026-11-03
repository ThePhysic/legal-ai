# Corpus provenance and reuse audit

The bundled corpus contains only statutory text from California Civil Code sections **1950.5**, **1950.6** and **1942.5**. It is a deliberately small California residential landlord–tenant collection, not a complete or continuously updated legal library.

## Actual capture

- Publisher: California Legislature, compiled and published by the California Department of Real Estate (DRE).
- Actual source PDF: https://www.dre.ca.gov/files/pdf/relaw/excerpts.pdf .
- Publisher's edition page: https://www.dre.ca.gov/Publications/RealEstateLaw.html identifies the 2026 compilation as of January 1, 2026.
- Full source PDF SHA-256: `f68f64e547b1836572a39721c060df9cf9cadf02362107bff514ecb75784b5d2`.
- Captured pages: 128–129 (1942.5), 143–149 (1950.5), 149–150 (1950.6); exact page sets and UTC timestamps are recorded per source in manifest.json.
- Actual current Legislature section URLs returned HTTP 403 in this environment. They remain related authority locators, not the claimed capture source. No access control was bypassed.

The raw compilation, images, seals and unrelated pages are not redistributed. Each tracked text snapshot has its own SHA-256 and version. Each passage has a versioned stable ID, exact text hash, PDF page range and deterministic paragraph-group locator. Groups/parts are extraction boundaries, not assertions about nested statutory subdivision numbering. Whitespace is normalized; no professional transcription/interpretation review is claimed. Reimporting changed source bytes requires a new corpus/benchmark revision and reviewed locators.

## Rights basis

This import selects **government edicts (legislative enactments)** rather than treating all government web content as freely reusable. The U.S. Copyright Office's Compendium, third edition, §313.6(C)(2), describes the government-edicts doctrine and the treatment of state legislative enactments: https://www.copyright.gov/comp3/chap300/ch300-copyrightable-authorship.pdf . Only the statutory language is included; no third-party annotations or editorial guide commentary.

DRE's own Conditions of Use, Ownership section, distinguishes public-domain information from separately protected content and official branding: https://www.dre.ca.gov/Conditions.html . No official seals, branding or photographs are reused, and this project claims no DRE or State endorsement. DRE brochure/publication reproduction conditions are not relied on to redistribute a guide in modified form.

California Courts guidance is **not ingested**. The Judicial Branch website terms restrict automated gathering and reuse of protected content (https://courts.ca.gov/es/node/33320); availability online is not a blanket license. The earlier UX proposal's short guidance example is a design reference, not this application's corpus.

This is an engineering source audit, not legal advice or professional rights clearance for expanding the collection. New publishers/material types require their own rights review.

## Applicability and refresh

`publication_as_of: 2026-01-01` records the publisher's edition, not an independently established legal effective-date interval. Both effective bounds remain null. Date-specific/historical applicability is therefore unresolved and the application must expose the gap or abstain. A capture on November 3 does not prove law remained unchanged through November or applies to any individual case. Local ordinances, later amendments, case treatment and exceptions outside the selected passages are not covered.

Offline verification: `python scripts/verify_corpus.py` checks hashes, exact passage membership, stable versioned IDs and size caps. Optional explicit refresh uses `python scripts/capture_corpus.py --download`, then requires renewed source/date/rights/locator review and a new frozen benchmark; normal startup never crawls or refreshes.
