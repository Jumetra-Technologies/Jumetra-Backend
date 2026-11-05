# Community API

`GET /community/stats` feeds the community section of the website's Advanced
Analytics page: what everyone has built in Kiungo, counted across every
account. It is public (no sign-in) and read-only, and holds only
platform-wide figures. Code: `api/services/community_stats.py`.

## What it returns

| Field | What |
| --- | --- |
| `totals` | Builders (accounts that have signed in), builders active in the last 30 days, projects, lab sessions, experiment records, parts placed, wires, runs, faults fixed, simulated hours, Learning Center modules completed. |
| `parts` | Parts by the number of lab sessions that use them (top 12). |
| `project_hardware` | Hardware named on projects, by the number of people listing it. |
| `categories` | Projects by category. |
| `modes` | Parts placed by mode: virtual, physical, hybrid. |
| `monthly` | The last 12 months: projects and lab sessions created, running totals to date, and people active (null when under the threshold). |
| `privacy` | `min_group` and `cache_seconds`, so the page can say what it holds back. |

Each breakdown is `{ rows: [{ key, count, people }], other: { count, people } | null }`.

## Privacy rules

- **No personal data.** No names, emails, ids or single records, ever.
- **Breakdown rows need 10 people** (`MIN_GROUP`). A part, category or mode
  that fewer than 10 people account for is folded into `other` and not
  named, so a part only one student has tried never points at that student.
  10 is the small-cell rule CMS uses for US health statistics.
- **Monthly counts always show** (a count of projects says nothing about who
  made them), so a young platform's chart isn't blank; the number of people
  active in a month is null under 10.
- **Cached 10 minutes** per process; `Cache-Control: public, max-age=300`.

## Keeping it public

The route answers GETs without a session today. When the authenticated-write
middleware starts requiring a session on GETs (remediation WP-1, ENG-002),
add `/community/stats` to the public list beside `/health` and
`/releases/latest`.
