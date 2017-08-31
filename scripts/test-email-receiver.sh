#! /bin/bash

export email_prefix=email
export email_bucket=yangmillstheory-budget
export csv_bucket=yangmillstheory-budget
export csv_key=budget.csv
export sns_topic_arn=arn:aws:sns:us-west-2:079529114411:budget-update-ok
python3 email-receiver/lambda.py
cat /tmp/budget.csv
