# Demo script

The demo runs on a local machine. It shows the six steps of plan WP9. The
run takes about six minutes. Every member of the team must be able to do
every step.

## Before the demo

* Start the backend and the frontend (see the README).
* Open the browser with the window in full screen (1920x1080) and hide the
  notifications.
* Prepare the BOM file `docs/demo_bom.csv`.
* Have the terminal with the evaluation ready in a second window.

```bash
make run-api      # terminal 1, 127.0.0.1:8000
make run-web      # terminal 2, 127.0.0.1:5173
```

Check the health of the API first:

```bash
curl -s http://127.0.0.1:8000/api/stats
```

The demo uses the local database. It never calls an external API during the
demo, so the demo works without a key and without a network.

## The six steps

### Step 1: the natural-language search (1 minute)

Type in the search box:

```
100 V N-channel MOSFET, Rds(on) below 5 mOhm, in stock
```

**Say:** "The query goes to the language model, the model builds a filter,
and the database executes the filter. The model never chooses the result."

Show:

* the filter chips under the search box (100 V, Rds(on) < 5 mOhm, in stock);
* the result table with the MPN, the manufacturer, the key values, the
  lifecycle badge and the stock.

Click one chip to show that the user can edit the filter.

### Step 2: the value and its source (1 minute)

Click a part to open the part page. Click the value of `Rds(on)`.

**Say:** "Every value shows its unit, its condition, its confidence and its
source. The side panel shows the page of the datasheet with the value
highlighted."

Show:

* the table of the values with the condition (for example `Vgs = 10 V,
  Tj = 25 C`);
* the confidence badge (green, yellow, red);
* the source viewer with the page image and the row of the table.

### Step 3: a value that the validator rejected (1 minute)

Open the review queue (`/review`).

**Say:** "The validator compares the value with the range of the field and
with the value of the distributor API. A value that does not match goes to
the review queue. Nothing wrong reaches the database."

Show:

* one row with a low confidence;
* the reasons of the row;
* the button that corrects the value.

Do not correct the value during the demo. Show that a person can.

### Step 4: the alternatives of an obsolete part (1 minute)

Open the alternatives of a part that has the badge `obsolete`.

**Say:** "The alternative finder takes the parts of the same family and the
same package, compares the key fields, rejects the parts that break a hard
rule and ranks the rest."

Show:

* the ranked list with the score and the reason (for example "lower
  Rds(on), higher Qg");
* one alternative that is rejected, with the reason.

### Step 5: the BOM check (1 minute)

Open the BOM page and upload `docs/demo_bom.csv`.

**Say:** "The BOM check reads the CSV, matches each line with a part and
flags the risk: an obsolete part, a part that is not in stock, a part with
only one source and a line that matches no part at all."

Show the risk table with the coloured badges.

### Step 6: the evaluation (1 minute)

Run in the terminal:

```bash
cd backend && .venv/bin/python -m eval demo
```

**Say:** "The six experiments of the evaluation plan. The accuracy per tier,
the cost saved by the tiered use, the wrong values that the validator stops,
the success of the 30 queries, the precision of the alternative finder and
the accuracy per manufacturer."

Show the charts in `eval/results/`:

* `accuracy_by_tier.png`;
* `cost_vs_accuracy.png`;
* `validation_confusion.png`;
* `accuracy_by_manufacturer.png`.

## The test data

| What | Where | Note |
| --- | --- | --- |
| The search query | step 1 | The query of the plan. |
| The part with a source | step 2 | A part that has a PDF and at least ten values. |
| The review item | step 3 | A value that the API disagrees with. |
| The obsolete part | step 4 | A part with the badge `obsolete` and alternatives. |
| The BOM file | `docs/demo_bom.csv` | 6 lines: a normal part, a low-stock part, an obsolete part, a single-source part and a line with a wrong MPN. |

The file `docs/demo_bom.csv` holds the header `mpn,quantity,manufacturer,reference`
and six lines. The wrong MPN is on purpose: it shows the unmatched line in
the risk table.

## The backup recording

The demo must work even if the network or the API is down on the day.

1. Record the whole demo with the screen recorder of the laptop. Use
   **OBS Studio** or the built-in recorder. Record the screen of the
   browser, not the whole desktop.
2. Save the file in the private folder of the team. Do **not** put a
   recording in the repository if it shows a key or a private URL.
3. Check the recording after the recording: the audio must be clear and the
   cursor must be visible.
4. Run the demo again with the recording ready, in case the live demo fails.
5. Take a screenshot of every step as a fallback. Put them in the slide
   deck.
6. Test the whole demo **the day before**. Use the checklist below.

## The checklist of the day before

- [ ] The backend starts and `/api/stats` answers.
- [ ] The frontend starts and the search page loads.
- [ ] The database holds at least the parts of the demo.
- [ ] The part of step 2 shows a page image in the source viewer.
- [ ] The review queue holds at least one row.
- [ ] The alternatives page of the obsolete part is not empty.
- [ ] `docs/demo_bom.csv` gives at least four risk rows.
- [ ] `python -m eval demo` writes the five charts.
- [ ] The recording is saved and it plays from the start to the end.
- [ ] Every member of the team can do every step.
