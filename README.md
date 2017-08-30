# budget

> Automate budget tracking

## Design

![system-diagram](./budget.png)

Two CSV files live in S3, a template budget file, and the active budget, which is a copy of the template, but partially filled.

Emails (essentially receipts) to a domain registered via Route53 trigger a Lambda that then updates the file on S3 and sends an SMS notification.

Using S3 as a data store isn't concurrency-safe, but traffic is low and spread far apart. Also, we don't need to persist the data for more than a given period (currently one week).

Periodically - currently every Saturday at 12AM PST - the budget is reset and a summary notification is sent via SMS.


## Getting started

```
$ brew install terraform  # or brew upgrade terraform if you have it
$ terraform init          # have to do this in the core modules as well
```

Need an email address to send email receipts to:

```
$ export TF_VAR_budget_email=
```

## Development

### AWS

```
$ terraform plan
$ terraform apply # writes state to S3
```

### Lambda


Test the email receiver.

```
$ ./test-email-receiver.sh
```

Test budget reset, which is invoked periodically by a CloudWatch event rule.

```
$ ./test-budget-reset.sh
```

### Checking results

Dump the current budget to stdout:

```
$ ./cat-budget.sh
```

Open the file (uses Excel if you have it):

```
$ ./open-budget.sh
```

## Monitoring

* [CloudWatch logs](https://us-west-2.console.aws.amazon.com/cloudwatch/home?region=us-west-2#logStream:group=/aws/lambda/email-receiver;streamFilter=typeLogStreamPrefix)
