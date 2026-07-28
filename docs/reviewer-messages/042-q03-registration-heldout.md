# Reviewer decision 042: Q03 registration held-out

Date: 2026-07-27

Decision: `REDIRECT`

Evidence anchor: `100`

## Independent audit

- Candidate hash remained frozen before and after held-out open: pass.
- Held-out open count: exactly `1`.
- C2 fit gate: `24.631505 mm <= 25 mm`, pass.
- B7 held-out gate: `164.353128 mm > 25 mm`, fail.
- Held-out vector recomputation from frozen route offset, actual apex, and v4
  physical-square mapping: pass.
- Perfect-tracking held-out replay introduced no external contact pairs:
  pass.
- Candidate tuning after held-out open: none.
- New registration family: forbidden.

V4 is rejected for metric registration. F1 is mandatory and must update the
claim before any action compilation: the only admissible prospective outcome
is complete displacement off the selected source square in both directions.
Destination-square placement cannot be claimed.

Q04 may proceed as a retrospective immutable-C2 diagnostic. Q04 cannot
promote v4 or erase this terminal held-out negative.
