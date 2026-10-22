# PartPilot: report skeleton

**Project:** AI-assisted component data mining for power MOSFETs and gate
drivers. Web Data Mining mini project, R5CO4201T.

This file is the skeleton of the report. Every section holds the headings, a
short note of what to write there and the place of the tables and the
charts. The target length is 8 to 10 pages.

The numbers come from the evaluation harness in `eval/`. The charts are in
`eval/results/`. Every number in the report must point to the file and the
command that produced it.

---

## 1. Introduction (0.75 page)

*What to write here.*

* The problem. A datasheet holds the truth about a part, but the truth is
  in a PDF that nobody reads. An engineer needs 12 numbers of a MOSFET and
  10 numbers of a gate driver, and the numbers have a unit, a condition and
  a page.
* Why it is hard. The value is in a table, the unit changes, the same field
  has three values (min, typical, max), the test condition changes the
  value, and the table is sometimes an image.
* The idea of PartPilot. Read the PDF in three tiers, check every value,
  keep the source with every value, and let the user search the data in
  plain language.
* What is new here. The tiered use of a language model for the extraction of
  datasheet tables, the cross-check of the extracted value against the
  distributor API, and the evaluation with a hand-labelled gold set.
* The contribution. A working system, an evaluation with six experiments on
  a gold set of 80 parts, a failure analysis and an ethics note.
* The limits in one sentence. The project is for study only and the data
  belongs to its owners.

*Insert:* Figure 1, the architecture diagram (the ASCII diagram of the
README or a Mermaid picture).

## 2. Related work (0.75 page)

*What to write here.*

* Datasheet parsing. The classical tools: table extraction with
  `pdfplumber` and `camelot`, layout analysis, the limits of the
  rule-based parsers on merged header cells and on multi-page tables.
* Information extraction with a language model. The move from a rule-based
  parser to a language model with a JSON schema. The cost and the risk of a
  hallucinated number.
* The datasheet data sets. The public data sets of component data and their
  limits (a small number of parts, no condition, no page).
* Electronic component search. The parametric search of the distributors and
  the gap between the search box and the datasheet.
* The difference of this project. The three tiers, the check against the
  API value, the source with every value, and the measured quality.

*Insert:* Table 1, the comparison of the related work. Columns: the work,
the data set, the method, the quality measure, the difference.

## 3. System design (1.5 pages)

*What to write here.*

* 3.1 The architecture. The nine modules of plan section 5. The data flow
  from the API to the screen.
* 3.2 The three tiers. The rule of plan section 5.1: call a higher tier
  only when the lower tier fails. The cost of a vision call against the
  cost of a text call.
* 3.3 The data model. The `parts`, `parameters`, `sources`, `offers`,
  `name_map` and `llm_calls` tables. Why every value carries the source,
  the page, the tier, the confidence, the condition and the status.
* 3.4 The validator. The unit conversion, the range rule, the check of
  min <= typ <= max, the cross-check against the API value, the confidence
  and the status.
* 3.5 The search. The chain that builds the filter, the database that
  executes it, and the reason that the language model never chooses the
  result.
* 3.6 The ethics by design. The rate limiter, the cache, the robots.txt
  check, the User-Agent and the download delay.

*Insert:* Figure 2, the sequence diagram of the extraction of one
datasheet. Figure 3, the diagram of the confidence model.

## 4. Implementation (1.5 pages)

*What to write here.*

* 4.1 The stack. Python 3.12, FastAPI, LangChain, Pydantic, pint,
  SQLAlchemy, React, shadcn/ui. The pinned versions.
* 4.2 The collectors. The three clients, the OAuth flow, the rate limiter
  below the documented limit, the cache with the date and the hash, the
  retry with a back-off.
* 4.3 The downloader. The robots.txt check, the 1 s delay, the check that
  the body is a PDF, the hash name.
* 4.4 The extractor. The tier 1 table parser and the regular expressions,
  the tier 2 chain with the JSON schema, the tier 3 chain with the page
  image. The prompt rules. The failure of a field instead of a guess.
* 4.5 The validator. The range rules, the confidence, the status.
* 4.6 The API and the frontend. The endpoints, the search page, the part
  page with the source viewer, the review queue, the dashboard.
* 4.7 The evaluation harness. The six experiments, the gold set, the
  metrics. Where the code lives.

*Insert:* Table 2, the endpoints and the frontend page that uses each of
them. Listing 1, the tier 1 regular expressions.

## 5. Experiments and results (2 pages)

*What to write here.*

Write every number from the files in `eval/results/`. Give the command that
produced each table.

* 5.1 The gold set. The number of parts, the number of manufacturers, the
  number of fields per part, the share of the double checked labels and the
  agreement rate.
* 5.2 Experiment 1, the tiers. The field accuracy, the cost and the time
  per tier. The answer to the acceptance test of WP4: tier 2 gives a higher
  field accuracy than tier 1 alone.
* 5.3 Experiment 2, the tiered use against the best tier. The cost that is
  saved at the same accuracy.
* 5.4 Experiment 3, the validation on and off. The number of wrong values
  that the validator stops. The answer to the acceptance test of WP5.
* 5.5 Experiment 4, the search. The query success on the 30 queries for the
  natural-language search and for the keyword search. The answer to the
  acceptance test of WP6: at least 80 %.
* 5.6 Experiment 5, the alternative finder. The precision at 3 against the
  opinion of the experts.
* 5.7 Experiment 6, the accuracy per manufacturer. Where the datasheets are
  hard.

*Insert:*

* Table 3, the accuracy, the cost and the time per tier.
  (`python -m eval demo` prints it as a markdown table.)
* Figure 4, the accuracy per tier: `eval/results/accuracy_by_tier.png`.
* Figure 5, the cost per tier: `eval/results/cost_by_tier.png`.
* Figure 6, the cost against the accuracy: `eval/results/cost_vs_accuracy.png`.
* Figure 7, the confusion matrix of the validation:
  `eval/results/validation_confusion.png`.
* Figure 8, the accuracy per manufacturer:
  `eval/results/accuracy_by_manufacturer.png`.
* Table 4, the query success of the search.
* Table 5, the precision at 3 of the alternative finder.

## 6. Failure analysis (1 page)

*What to write here.*

* The list of the most common errors. Take it from the labels of the wrong
  values of the gold set.
* One example for each error, with the page of the datasheet and the text
  that caused it.
* The reason for each error: a merged table cell, a unit in the header, a
  value that depends on the condition, an image table, a symbol that is not
  in the name map, a footnote.
* What the system does with each error: a failed field, a value in the
  review queue, a rejected value.
* What a better name map, a better prompt or a better table parser would
  fix. Say which fix gives the most accuracy for the least work.

*Insert:* Table 6, the most common errors with the number of cases, an
example and the fix.

## 7. Limits and future work (0.5 page)

*What to write here.*

* The limits of the data. Two families. A gold set of 80 parts. English
  datasheets. A free plan of the APIs.
* The limits of the method. The extraction reads a table, it does not read a
  graph. The confidence is a rule, not a learned number. The search needs
  the LLM for every query.
* The limits of the measurement. The gold set is small, so the numbers have
  a wide interval. The cost depends on the price of the model on the day of
  the run.
* The future work. The graphs, the third family, the KiCad export, the
  active learning of the name map, the price of the parts in the search.

## 8. Ethics (0.5 page)

*What to write here.*

Summarise `docs/ETHICS.md`. The ten rules of plan section 12, the
documented limits of the three APIs, the 1 s delay, the User-Agent, the
cache, the fact that no datasheet PDF is in the repository, and the warning
that the project is for study only.

*Insert:* the table of the limits of the three APIs.

## 9. Conclusion (0.25 page)

*What to write here.*

* The answer in three sentences: what was built, what the numbers show, and
  what a reader should take away.
* The one sentence that names the next step.

## 10. References (0.5 page)

*What to write here.*

Use one style for the whole list. Give the author, the title, the
publisher or the journal, the year and the URL or the DOI.

1. The DigiKey Product Information API v4 documentation.
2. The Nexar (Octopart) API documentation.
3. The Mouser Search API documentation.
4. The LangChain documentation for the structured output, the rate limiter
   and the cache.
5. The pint documentation for the units.
6. The pdfplumber and the PyMuPDF documentation.
7. The papers on table extraction from PDF files.
8. The papers on information extraction with a language model and on the
   hallucination of numbers.
9. The papers on parametric search of electronic components.
10. The public datasheet data sets.

---

## Checklist before the submission

- [ ] Every number in the report comes from a file in `eval/results/`.
- [ ] Every chart in the report is in `eval/results/`.
- [ ] The gold set has 80 parts, 5 manufacturers and a second check of 20 %.
- [ ] The agreement rate is in section 5.1.
- [ ] The six experiments have a table and a chart.
- [ ] The failure analysis names at least five errors with an example.
- [ ] The ethics note is complete.
- [ ] The references use one style and every URL works.
