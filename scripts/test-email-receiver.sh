#! /bin/bash

export email_prefix=budget
export email_bucket=yangmillstheory-email
export allowed_senders=v.alvarez312@gmail.com
export csv_bucket=yangmillstheory-budget
export csv_key=budget.csv
export sns_topic_arn=arn:aws:sns:us-west-2:079529114411:budget-update-ok
export dry_run=1
python3 receive/lambda.py
cat /tmp/budget.csv
