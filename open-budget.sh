#! /bin/bash

aws s3 cp s3://yangmillstheory-budget/budget.csv .budget.csv
echo "Downloaded budget to .budget.csv."
echo "Opening..."
open .budget.csv
