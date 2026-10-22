# The PartPilot evaluation harness

The harness measures the system with the six experiments of plan WP8. It is
standalone: it imports nothing from another agent's package, it never opens
a database connection and it never calls a network API. Every experiment
takes the implementation that it measures through injection, so the same
functions measure the fake code in the tests, the fixture backed demo and
the real code.

## Run it

The harness lives in the repository root. The backend virtual environment
runs it:

```bash
cd backend

.venv/bin/python -m eval --help
.venv/bin/python -m eval demo                                  # the six experiments
.venv/bin/python -m eval validate-gold ../eval/gold_set.csv    # check a gold set
.venv/bin/python -m eval agreement ../eval/gold_set.csv        # the agreement rate
.venv/bin/python -m eval queries                               # the 30 test queries
.venv/bin/python -m eval charts ../eval/results/demo_results.json
```

The tests of the harness:

```bash
cd backend && .venv/bin/python -m pytest ../eval -q
```

The lint of the harness uses the configuration of the backend:

```bash
cd backend
.venv/bin/python -m ruff check --config pyproject.toml ../eval
.venv/bin/python -m black --check --config pyproject.toml ../eval
```

## The files

| File | Content |
| --- | --- |
| `eval/metrics.py` | The metric functions. Each one is pure and has its own test. |
| `eval/gold_set.py` | The loader, the validator and the agreement report of the gold set. |
| `eval/runners.py` | The six experiments. |
| `eval/queries.py` | The 30 natural-language search queries. |
| `eval/charts.py` | The five matplotlib charts. |
| `eval/demo.py` | The fake implementations and the demo run. |
| `eval/__main__.py` | The command line. |
| `eval/gold_set_template.csv` | The format of the gold set, with three example rows. |
| `eval/results/` | The result files and the charts. They are not in Git. |

## The metrics

| Function | What it measures |
| --- | --- |
| `field_accuracy(predictions, gold)` | The share of the gold `(part, parameter)` pairs that the prediction gets right. A missing prediction is wrong. The tolerance is 5 % relative, or an absolute tolerance for a tiny value. |
| `values_match(a, b, tolerance)` | The comparison of two values. The units are converted first. |
| `normalise_value(value, unit)` | The conversion of a value to the canonical unit of its dimension. |
| `precision_at_k(retrieved, relevant, k)` | The share of the first `k` results that is relevant. |
| `recall(retrieved, relevant)` | The share of the relevant items that the result list holds. |
| `mrr(ranked, relevant)` | The reciprocal rank of the first relevant item. |
| `refusal_rate(results, refusals)` | The share of the questions that the system refused to answer. |
| `cost_per_datasheet(calls)` | The average cost of the LLM calls of one datasheet. |
| `latency_stats(durations_ms)` | The mean, the median and the p95 of the durations. |
| `confusion(true_labels, predicted_labels)` | The confusion matrix of the validation experiment: how many wrong values were stopped. |
| `accuracy_by_manufacturer(results)` | The field accuracy per manufacturer. |
| `accuracy_by_field(results)` | The field accuracy per parameter name. |

## The experiments

### Experiment 1: the tiers

`experiment_1_tiers(extractor, gold, parts=None, tiers=None, cost_fn=None, time_fn=None)`

It compares tier 1, tier 2 with the text only, tier 2 with the tables and
tier 3. It measures the field accuracy, the cost and the time of each tier.

The extractor is an object with the methods `tier1`, `tier2_text`,
`tier2_tables` and `tier3`. Each method takes a `part_id` and returns the
outcome of the part. The outcome may be:

* a mapping of the parameter name to the value;
* a list of the parameter objects;
* an object with a `values` list (the `ExtractionResult` of the contract);
* a dictionary with the keys `values`, `cost` and `duration_ms`.

The extractor may also be a mapping `{tier: {part_id: outcome}}` or a
mapping `{tier: extractor}`.

### Experiment 2: the tiered use against the best tier

`experiment_2_tiered_vs_best(tiered_results, best_tier_results)`

Both arguments hold an `accuracy` and a `cost`. The result holds the cost
that the tiered use saves, the share of that saving and the difference of
the accuracy.

### Experiment 3: the validation on and off

`experiment_3_validation_on_off(validated, unvalidated)`

Each argument holds one record per value. A record holds the gold value, the
predicted value and the status. The status `rejected` or `review` means that
the validator stopped the value. The result counts the wrong values that the
validator stops and holds the confusion matrix.

### Experiment 4: the natural-language search

`experiment_4_search(nl_results, keyword_results, queries)`

The queries are the 30 pairs of `eval/queries.py`. The natural-language
result holds the filter that the service built. The keyword result holds
the number of results, or a mapping with a `total` key. The result holds the
success rate of the two searches. The plan asks for at least 80 %.

### Experiment 5: the alternative finder

`experiment_5_alternatives(ranked, expert_labels)`

The ranking holds the alternatives per part. The expert labels hold the
alternatives that the experts accept. The result holds the precision at 3,
the precision at 1, the recall and the mean reciprocal rank.

### Experiment 6: the accuracy per manufacturer

`experiment_6_by_manufacturer(results)`

The result holds the field accuracy per manufacturer.

## Add a gold set

1. Copy the template.

   ```bash
   cp eval/gold_set_template.csv eval/gold_set.csv
   ```

2. Fill in the rows. The format is in `docs/GOLD_SET.md`. The columns are
   `part_id,mpn,manufacturer,family,param_name,value,unit,condition,labelled_by,second_check_by,agreement,notes`.

3. Check the file.

   ```bash
   cd backend && .venv/bin/python -m eval validate-gold ../eval/gold_set.csv
   ```

   The command prints one line per problem and returns `1` when the file has
   a problem. It checks the header, the number in the value, the unit, the
   duplicate pair, the name of the labeller and the value of the agreement.

4. Read the agreement.

   ```bash
   cd backend && .venv/bin/python -m eval agreement ../eval/gold_set.csv
   ```

5. Measure the system with the gold set. Write a script that builds the
   real implementation and calls the six experiments. The demo shows the
   shape of such a script.

## The result file and the charts

The demo writes `eval/results/demo_results.json`. The charts read the same
shape:

```json
{
  "tiers": {"tier1": {"accuracy": 0.5, "cost": 0.0, "duration_ms": 1000}},
  "manufacturers": {"TI": {"accuracy": 0.9, "correct": 9, "total": 10}},
  "confusion": {"labels": ["accepted", "wrong"], "matrix": [[8, 0], [0, 2]]},
  "cost_vs_accuracy": [{"name": "tier1", "cost": 0.0, "accuracy": 0.5}]
}
```

The five charts are `accuracy_by_tier.png`, `cost_by_tier.png`,
`accuracy_by_manufacturer.png`, `validation_confusion.png` and
`cost_vs_accuracy.png`.

The charts need `matplotlib`. The package is not in `backend/pyproject.toml`
yet: `docs/CHANGE_REQUESTS/i-eval-docs-1.md`. Without the package the
chart functions raise `eval.charts.ChartsUnavailable` and the other parts
of the harness still work.

## The rules of the harness

* A real API call and a real language model call never happen in a test.
  The tests use the recorded fixtures of `contracts/fixtures/`.
* The gold set file and the result files are never in Git.
* No datasheet PDF is in Git.
