#! /bin/bash

export csv_bucket=yangmillstheory-budget
export csv_key=budget.csv
export csv_template_key=budget.csv.tmpl
export sns_topic_arn=arn:aws:sns:us-west-2:079529114411:budget-reset
# export dry_run=1
export max_period_spend=250
python3 reset/lambda.py

