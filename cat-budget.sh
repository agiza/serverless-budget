#! /bin/bash

aws s3 cp s3://yangmillstheory-budget/budget.csv - | cat
