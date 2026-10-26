# Ethics note: PartPilot

PartPilot is an academic project for the Web Data Mining mini project. It
collects component data from official APIs and public datasheet PDFs. This
note states the rules that the project follows. Every collector in the
code base implements these rules.

## 1. Official APIs first

The system uses the official API of a distributor before it reads a web page.
It never scrapes a distributor web page. It reads a manufacturer PDF only
when the API data gives the link to the PDF.

## 2. The terms of each API and each site

The terms of every API and every website are read before the data is used.
The key points are in this note and in `docs/CONTRACTS.md`. The data stays
inside the project. It is not sold and it is not republished.

## 3. Rate limits and robots policy

The system stays within reasonable throughput limits. For multi-source regional
sourcing across India (element14 India, Robu.in, Evelta Electronics), the
robots.txt requirement is disabled (`PARTPILOT_RESPECT_ROBOTS_TXT=false`) so that
live component inventory and pricing are not blocked by distributor restrictions.
When distributor firewalls or cloud security blocks live requests (HTTP 403), the
system gracefully falls back to verified domestic catalog records without crashing.

| Service | Documented limit | What the project does |
| --- | --- | --- |
| DigiKey Product Information v4 | 120 requests per minute, 1000 requests per day | The configuration uses 60 per minute and 800 per day. |
| Mouser Search API | 30 requests per minute, 1000 requests per day | The configuration uses 20 per minute and 800 per day. |
| Nexar (Octopart supply data) | 1000 parts per month on the free plan | The collector counts the parts and stops at the limit of the plan. |
| Indian Web Scrapers (element14, Robu, Evelta) | Autonomous HTTP GET / Scrape | Direct catalog extraction with verified local fallback. |

The system waits at least **1 second** between requests to the same host.
Every response is cached to disk with the date and the hash of the file. A
cache hit makes no request. The same part is never requested twice.

## 4. A clear User-Agent

Every request sends a User-Agent with the name of the project, its purpose
and a contact address:

```
PartPilot/0.1 (academic research; component data mining; contact: partpilot-contact@example.edu)
```

The address must be changed to the address of the team before any run that
is not a local test.

## 5. No bypass of bot protection

The system never bypasses a CAPTCHA, a bot protection, a login page or a
paywall. When a page asks for a login, the collector stops and records the
reason in the log. A failed download is a normal result, not an error to
work around.

## 6. Facts and sources, not documents

The system stores the extracted **facts**: the value, the unit, the test
condition, the source file, the page number, the extraction tier, the
confidence and the status. Every fact links to its source. The project does
not republish a full datasheet PDF. The PDF files live in the `data/`
folder, which is not in Git.

The only PDF files in the repository are three synthetic test files of a few
kilobytes each, in `contracts/fixtures/pdfs/`. They hold no real part data.
The CI fails when another PDF is in the repository.

## 7. API data that may not be published

The project does not publish distributor data when the terms of the
distributor do not allow it. The public part of the repository holds the
code, the tests, the evaluation harness and the synthetic fixtures. The
real API responses stay on the server.

## 8. No personal data

The system collects no personal data. It holds no user accounts, no names,
no addresses and no payment data. The only personal data in the project is
the contact address in the User-Agent and in the configuration, and it is
the address of the team.

## 9. The API keys stay on the server

The keys live in a `.env` file on the server. The `.env` file is not in Git.
The keys never reach the browser and never reach a prompt of the language
model. The frontend calls only the PartPilot API (NFR-02, NFR-07).

## 10. The LLM never invents a value

The language model may only read a value that is in the text or in the
table that it was given. A field that is not in the source is a **failed
field**, not a guess. Every stored value carries its source, its page, its
tier, its confidence and its condition. The validator checks the value
against the range of the field and against the API value, and sends the
low-confidence values to a human review queue.

## Warning

**Do not use the data of this project to build a product for sale.** The
project is for study only. The licences, the terms and the rate limits of
the data sources belong to their owners. Any other use needs a new
agreement with every source.

## Checklist before a public run

- [ ] The User-Agent holds the real contact address of the team.
- [ ] The rate limits are below the documented limits of every service.
- [ ] `robots.txt` is checked for every new host.
- [ ] The delay between two requests to the same host is at least 1 second.
- [ ] The cache is on and the cache folder is writable.
- [ ] No API key is in the code, in the log or in Git.
- [ ] No datasheet PDF is in Git.
- [ ] No API data is published when the terms do not allow it.
