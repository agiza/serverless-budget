# budget

> Automate budget tracking

## Getting started

```
$ brew install terraform  # or brew upgrade terraform if you have it
$ terraform init          # have to do this in the core modules as well
```

Need to send the email to send budget updates to (keeping this private):

```
$ export TF_VAR_budget_email=
```

## Development

To make infrastructure changes

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


## Monitoring

* [CloudWatch logs](https://us-west-2.console.aws.amazon.com/cloudwatch/home?region=us-west-2#logStream:group=/aws/lambda/email-receiver;streamFilter=typeLogStreamPrefix)
