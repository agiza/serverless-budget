#! /bin/bash

export AWS_PROFILE=yangmillstheory
export allowed_senders=v.alvarez312@gmail.com,hchaides@gmail.com
export email_prefix=budget
export email_bucket=yangmillstheory-email
export csv_bucket=yangmillstheory-budget
export csv_key=budget.csv
export sns_topic_arn=arn:aws:sns:us-west-2:079529114411:budget-update-ok
export dry_run=1
export max_period_spend=250
python3 receive/lambda.py
cat /tmp/budget.csv
