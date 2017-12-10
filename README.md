# serverless-budget

> Automated budget tracking


[Read this blog post for motivation and design.](https://blog.yangmillstheory.com/posts/serverless-budget-tracking/)

## Getting started

Make sure your AWS credentials are installed and configured. (The source code assumes my own AWS profile, tweak accordingly.)

Install `terraform`:

```
$ brew install terraform  # or brew upgrade terraform if you have it
$ terraform init
```

Need email addresses to send email receipts from and send period results to:

```
$ export TF_VAR_budget_email=     # where to send receipts to
$ export TF_VAR_allowed_senders=  # comma-separated email addresses
$ export TF_VAR_reset_recipients= # comma-separated email addresses
```

before `terraform plan` and `terraform apply`.

## Development

### AWS

```
$ terraform plan
$ terraform apply # writes state to S3
```

### Lambda

Test the email receiver.

```
$ ./scripts/test-receive.sh
```

Test budget reset, which is invoked periodically by a CloudWatch event rule.

```
$ ./scripts/test-budget-reset.sh
```

### Checking results

Dump the current budget to stdout:

```
$ ./scripts/cat-budget.sh
```

Open the file (uses Excel if you have it):

```
$ ./scripts/open-budget.sh
```
