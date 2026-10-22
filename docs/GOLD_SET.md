# Building the gold set

The gold set is the test set of the project. It holds the values that a
person read in the datasheet and checked by hand. The system is measured
against this set (plan WP8, step 1).

The plan asks for:

* **80 parts**;
* at least **5 manufacturers**;
* **10 to 15 fields** for each part;
* a second member checks **20 %** of the labels;
* the **agreement** between the two members is recorded.

## 1. The parts

Use the seed list in `contracts/fixtures/seed/seed_parts.csv`. It holds 30
parts. Extend it to 80 parts with the same rule: at least five
manufacturers, and both families in the set.

| Family | Parts | Note |
| --- | --- | --- |
| Power MOSFET | 50 | The main family of the project. |
| Gate driver | 30 | The second family. |

Spread the parts over at least five manufacturers. A good spread for the
MOSFETs is Infineon, onsemi, Nexperia, STMicroelectronics, Vishay,
Diodes, Alpha & Omega, International Rectifier and Texas Instruments. Use
the datasheet that the API gives for each part. Keep the same file for the
whole set.

One part is one PDF. Parts that share a datasheet are still separate parts
in the gold set.

## 2. The fields

Label the fields of plan section 7.1.

**Power MOSFET (13 fields):** `vds_max`, `id_continuous`, `rds_on`,
`vgs_threshold`, `vgs_max`, `total_gate_charge_qg`, `gate_drain_charge_qgd`,
`input_capacitance_ciss`, `output_capacitance_coss`, `max_junction_temp`,
`package`, `thermal_resistance`, `reverse_recovery_qrr`.

**Gate driver (12 fields):** `supply_voltage_min`, `supply_voltage_max`,
`peak_source_current`, `peak_sink_current`, `input_logic_level`,
`propagation_delay`, `rise_time`, `fall_time`, `uvlo_threshold`,
`channel_count`, `package`, `operating_temp_min`, `operating_temp_max`.

Use the standard names. The `name_map` table of the database holds the
mapping from the name in the datasheet to the standard name. A new name
needs the approval of a second member.

## 3. How to label one value

1. Open the datasheet of the part.
2. Find the table with the value. Write the page number in the `notes`
   column.
3. Copy the value into the `value` column. Use the number only. No text,
   no range and no unit in the value column.
4. Write the unit in the `unit` column. Use the unit of the datasheet.
5. Write the test condition in the `condition` column as a JSON object, for
   example `{"Id": "2 A", "Tj": "25 C", "Vgs": "10 V"}`. A value without a
   condition is a bad label: the same field has a different value at a
   different condition.
6. Write the minimum, the typical and the maximum in the `notes` column
   when the datasheet gives three values, for example
   `min 2.0, typ 3.5, max 4.5 on page 4`.
7. Write your name in the `labelled_by` column.

A label that you did not find is **not** a label. Leave the row out. A
missing field is a failed field of the system, not a wrong value of the
gold set.

## 4. The format

The format is the format of `contracts/fixtures/gold/gold_set_example.csv`.
The template with three example rows is `eval/gold_set_template.csv`.

```
part_id,mpn,manufacturer,family,param_name,value,unit,condition,labelled_by,second_check_by,agreement,notes
```

| Column | Meaning |
| --- | --- |
| `part_id` | The id of the part in the database. Use the same id as in the `parts` table. |
| `mpn` | The manufacturer part number. |
| `manufacturer` | The name of the manufacturer. |
| `family` | `mosfet` or `gate_driver`. |
| `param_name` | The standard name of the field. |
| `value` | The number. No unit. |
| `unit` | The unit of the value. |
| `condition` | A JSON object with the test condition. |
| `labelled_by` | The name of the member that read the value. |
| `second_check_by` | The name of the member that checked the value. Empty for a first label. |
| `agreement` | `yes` or `no`. Empty for a first label. |
| `notes` | The page number, the min/typ/max, or any other note. |

## 5. The second check

A second member checks **20 %** of the labels. Use a random sample, not the
first rows of the file. The checker reads the value again in the datasheet
and writes:

* their name in `second_check_by`;
* `yes` in `agreement` when the value and the condition are the same;
* `no` in `agreement` when the value or the condition is different;
* a short note in `notes` when the two members disagree.

A row with a `second_check_by` and an empty `agreement` is *not recorded*.
The agreement report counts it apart from a disagreement.

## 6. Check the file

The validator finds the broken rows before the evaluation uses the file.

```bash
cd backend && .venv/bin/python -m eval validate-gold ../eval/gold_set.csv
```

The command prints one line per problem and returns `1` when the file has a
problem. It checks that:

* the header holds every column of the format;
* every `value` is a number;
* every numeric row has a unit;
* every `(part_id, param_name)` pair appears once;
* every row has a `labelled_by`;
* every `agreement` is `yes`, `no` or empty.

## 7. Read the agreement

```bash
cd backend && .venv/bin/python -m eval agreement ../eval/gold_set.csv
```

The command prints the number of rows, the number of double checked rows,
the share of the double checked rows, the agreement rate and the agreement
per first labeller. The number of the double checked rows must be at least
20 % of the rows. The agreement rate must be in the report.

## 8. Measure the system

The six experiments of plan WP8 read the gold set. The demo shows the
harness on the recorded fixture:

```bash
cd backend && .venv/bin/python -m eval demo
```

The real run uses the same functions with the real implementation injected.
See `eval/README.md`.
