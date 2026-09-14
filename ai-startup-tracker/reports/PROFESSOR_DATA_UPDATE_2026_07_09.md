# Professor Data Update - 2026-07-09

Railway DB snapshot checked after today's ingestion run.

## Current Railway Totals

| Table | Rows |
|---|---:|
| companies | 986,326 |
| funding_signals | 269,181 |
| incubator_signals | 33,844 |
| news_articles | 446 |
| scrape_runs | 882 |
| site_health | 296 |

## Today's Increment by Source

Companies created since 2026-07-09 10:00 UTC: 8,157.

| Source / approach | New companies in Railway | Supporting evidence |
|---|---:|---|
| NIH SBIR/STTR grants | 5,282 | `companies.source_domain = 'nih.gov'` |
| NSF SBIR/STTR grants | 2,399 | `companies.source_domain = 'nsf.gov'` |
| Government grants total | 7,681 | Import log: `new=7681`, `enriched=304`, `already_known=6441` |
| News discovery | 174 | Companies inserted from regional startup media feeds |
| Agentic portfolio/orchestrator scrape | 300 | New companies with non-news/non-government `source_domain` |
| Other/uncategorized today | 2 | Today's rows with null/other source |

## News Discovery Detail

| Metric | Count |
|---|---:|
| Processed news articles recorded | 446 |
| News funding signals | 200 |
| New companies from news feeds | 174 |

Top news feeds by new companies:

| Feed | New companies |
|---|---:|
| betakit.com | 58 |
| venturesquare.net | 26 |
| thebridge.jp | 14 |
| yourstory.com | 14 |
| startupdaily.net | 10 |
| techcrunch.com | 10 |
| eu-startups.com | 8 |
| tech.eu | 7 |
| arcticstartup.com | 6 |
| disruptafrica.com | 6 |

## Agentic Scrape Detail

| Metric | Count |
|---|---:|
| Scrape runs today | 120 |
| Successful scrape runs today | 56 |
| Records found | 7,647 |
| New companies inserted | 300 |

Top portfolio/source domains by new companies:

| Domain | New companies |
|---|---:|
| kakao.vc | 199 |
| zgcgroup.com.cn | 18 |
| industrifonden.se | 15 |
| lmarks.com | 15 |
| matrix.vc | 11 |
| nif.vc | 10 |
| startupinspire.com | 9 |
| iangels.com | 5 |
| vertexholdings.com | 4 |
| sparklabssaudi.com | 3 |

## GitHub Discovery Status

GitHub discovery is still running. It has found 20,352 candidate repos and has
processed 4,600 so far. The script writes to `github_signals` and
`github_repo_snapshots` at the end of the run, so current Railway GitHub counts
are still 0 until that process finishes.

## Operational Note

The government grants and news data are already in Railway. The orchestrator was
stopped after Anthropic returned a low-credit error, to avoid marking good sites
as failed for a billing issue.
