# Why WordPress/gutenberg Open Issues Grew, Stalled, Then Declined

Generated on 2026-06-11 from authenticated GitHub REST API data.

## Short Answer

The five-year open-issue curve is best explained by a combination of changing inflow and backlog management:

1. Growth from 2021 to early 2024 was mostly an inflow problem: new issues consistently exceeded closures.
2. The plateau in 2024 happened because inflow slowed while closure throughput stayed roughly steady.
3. The decline after early 2025 is not a single-cause story. It combines a sharp drop in newly opened GitHub issues with several cleanup waves closing older backlog.

The evidence does not support a clean "Gutenberg stopped using GitHub issues for project management" explanation. Maintainer-created issue share stayed broadly stable, but the absolute volume of both maintainer-created and community-created issues fell. It also does not prove "there are legitimately fewer product problems" in the broad product-quality sense, although fewer confirmed product-problem reports are now entering this GitHub repository.

## Data Collected

- Full issue inventory through 2026-06-11: 32,135 issues, excluding pull requests.
- Quarterly flow metrics: created issues, closed issues, net flow, open-at-end, creator counts, closure age, labels, author association, state reason.
- Monthly flow metrics for inflection timing.
- Deterministic qualitative samples:
  - 45 growth-created issues.
  - 45 plateau-created issues.
  - 45 decline-created issues.
  - 45 old issues closed during the decline period.
  - 30 recent issues closed during the decline period.

Period definitions:

- Growth: 2021-06-11 through 2024-03-31.
- Plateau: 2024-04-01 through 2025-03-31.
- Decline: 2025-04-01 through 2026-06-11.

Full-quarter averages below exclude the partial boundary quarters 2021-Q2 and 2026-Q2.

## Quantitative Findings

| Period | Full quarters | Avg created/q | Avg closed/q | Avg net/q | Avg unique creators/q | Avg first-time creators/q | Avg old closures/q | Open at first full q end | Open at last full q end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Growth | 11 | 967.6 | 737.8 | +229.8 | 333.0 | 121.3 | 169.5 | 3,329 | 5,640 |
| Plateau | 4 | 785.8 | 660.8 | +125.0 | 288.2 | 97.2 | 169.0 | 5,887 | 6,140 |
| Decline | 4 | 534.0 | 637.5 | -103.5 | 203.2 | 62.5 | 274.8 | 5,978 | 5,726 |

The inflection is visible before the big cleanup wave:

- 2025-01 through 2025-03 had only 162, 139, and 141 new issues per month.
- 2025-04 through 2025-06 had only 98, 81, and 92 new issues per month.
- The largest old-backlog cleanup signal came later: 2025-Q4 closed 1,038 issues, including 539 that had been open at least a year.
- December 2025 alone closed 375 issues, 245 of them at least a year old.
- The partial June 2026 data through June 11 shows another cleanup-like month: 68 created, 192 closed, 145 old closures.

## Are Fewer People Reporting?

Yes, in GitHub issues.

Average unique creators per full quarter fell:

- Growth: 333.0
- Plateau: 288.2
- Decline: 203.2

Average first-time creators per full quarter fell:

- Growth: 121.3
- Plateau: 97.2
- Decline: 62.5

Both maintainer and community issue creation fell in absolute terms:

| Period | Created issues | Maintainer-created | Community-created | Bot-created |
|---|---:|---:|---:|---:|
| Growth | 10,644 | 6,415 (60.3%) | 3,715 (34.9%) | 514 (4.8%) |
| Plateau | 3,143 | 1,964 (62.5%) | 1,139 (36.2%) | 40 (1.3%) |
| Decline | 2,136 | 1,329 (62.2%) | 764 (35.8%) | 43 (2.0%) |

Because the shares are similar, this looks like an overall GitHub issue inflow drop, not just one group leaving.

## Are Gutenberg Issues Used Less For Project Management?

Somewhat in absolute terms, but it is not enough to explain the curve by itself.

Project-management proxies:

- Maintainer-created issue share stayed stable: about 60-62%.
- Maintainer-created volume dropped substantially: 583.2 per quarter in growth to 332.2 per quarter in decline.
- Tracking/task-title issues became less common: 0.85% of created issues in growth, 0.51% in plateau, 0.37% in decline.
- Assigned-created issue share did not decline; it rose from 30.7% in growth to 39.3% in decline.

The qualitative samples still found active roadmap and maintainer-planning work in the decline period, including feature and release areas such as Notes, real-time collaboration, client-side media, DataViews, and navigation. So the better reading is: fewer issue-based PM artifacts are being created in absolute terms, but GitHub issues are still being used for project work, and the open-count decline is not mainly a PM migration artifact.

## Are There Legitimately Fewer Problems?

There are fewer new problem reports entering GitHub issues, but the data does not prove the product has proportionally fewer real-world problems.

Evidence for fewer GitHub problem reports:

- Created bug-labeled issues averaged 345.5 per quarter in growth, 411.8 in plateau, and 237.5 in decline.
- Needs-triage style created issues averaged 90.2 per quarter in growth, 67.0 in plateau, and 27.8 in decline.
- Community-created issues fell from 337.7 per quarter in growth to 191.0 in decline.

Evidence against overclaiming product-quality improvement:

- Equal-sized qualitative created samples still had similar confirmed-product-problem counts: growth 22/45, plateau 24/45, decline 23/45.
- Decline-created samples had more lower-problem-load/support/ownership signals: 30/45 in decline versus 26/45 in plateau and 4/45 in the growth sample coded by a separate agent.
- Closed old-backlog samples contained many closures that were cleanup, scope shift, stale/superseded work, or consolidation, not one-to-one fixes.

The most defensible conclusion is: fewer confirmed problem reports are reaching this GitHub repo, and some sampled decline-period issues look more like planning/tooling/support/ownership work. That may reflect product maturity, changed contributor focus, changed reporting behavior, or adjacent-channel routing. It is not enough by itself to say the software has fewer user-facing problems.

## Did Closures Increase Because Problems Were Fixed?

Partly, but backlog cleanup is a major component.

Decline-period closure sample:

| Code | Old closures, n=45 | Recent closures, n=30 |
|---|---:|---:|
| FIXED_BY_CHANGE | 24 | 20 |
| CONFIRMED_PRODUCT_PROBLEM | 18 | 18 |
| CLOSED_WITHOUT_RESOLUTION | 14 | 5 |
| SCOPE_OR_OWNERSHIP_SHIFT | 14 | 7 |
| LOWER_PROBLEM_LOAD_SIGNAL | 17 | 4 |
| DUPLICATE_OR_CONSOLIDATED | 6 | 3 |

Interpretation:

- Recent closures more often look like targeted fixes, active duplicate consolidation, or normal short-cycle issue handling.
- Old closures skew toward long-lived cleanup: stale/superseded items, changed implementation surfaces, scope/ownership shifts, and consolidation into newer trackers.
- Therefore, the declining open count should not be read as pure problem resolution. It includes real fixes, but also meaningful backlog pruning.

## Did Reporting Move Elsewhere?

The sampled GitHub threads do not show enough explicit redirects to make this the primary explanation.

Channel redirects were rare in the coded created samples:

- Growth: 2/45
- Plateau: 1/45
- Decline: 2/45

Scope/ownership shifts were more visible in decline than plateau, but still not dominant in created samples:

- Plateau: 1/45
- Decline: 3/45

This analysis did not crawl WordPress Trac, support forums, Slack, GitHub Discussions, or Make/Core posts. So it cannot rule out off-GitHub reporting changes. It can only say the sampled GitHub issues do not contain enough explicit redirect evidence to make channel migration the main observed cause.

## Why The Chart Shape Looks The Way It Does

Growth:

- New issues consistently exceeded closures by about 230 per quarter.
- Both user reports and maintainer project work were common in samples.
- Growth-created sample codes: USER_REPORT 25/45, MAINTAINER_PM 24/45, CONFIRMED_PRODUCT_PROBLEM 22/45, FIXED_BY_CHANGE 16/45.

Plateau:

- Inflow slowed from about 968 to 786 created issues per quarter.
- Closure volume also dipped, but the gap narrowed.
- Q4 2024 was almost flat: 806 created, 863 closed.
- Q1 2025 had a large creation drop: 442 created, 416 closed.

Decline:

- Created volume fell further to about 534 per full quarter.
- Closure volume averaged about 638 per full quarter.
- Late 2025 added a distinct old-backlog cleanup wave.
- Decline-created sample codes still show confirmed problems, but also more lower-load, support, ownership, and planning signals.

## Caveats

- GitHub issue labels are current labels, not necessarily labels at creation.
- `state_reason` is current API state, not a detailed closure rationale.
- GitHub REST issue data does not expose a reliable historical GitHub Projects usage trail.
- Reopened issue histories can affect point-in-time open counts; the inventory method uses current issue `created_at` and `closed_at`.
- Qualitative coding is sampled and interpretive. It was used to identify mechanisms, not to estimate exact repository-wide percentages.
- No off-GitHub reporting channels were crawled.

## Artifacts

- `fetch_gutenberg_data.py`: authenticated GitHub data pull and sampling.
- `issues_inventory.csv`: full public issue metadata inventory.
- `quarterly_metrics.csv`: quarterly flow table.
- `monthly_metrics.csv`: monthly flow table.
- `flow_and_open_issues.svg`: flow chart.
- `quantitative_summary.md`: quantitative summary.
- `samples/coded_*.csv`: qualitative coding outputs.
- `samples/coded_*_summary.md`: coding summaries.
