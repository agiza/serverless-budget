provider "aws" {
  region  = "us-west-2"
  profile = "yangmillstheory"
}

# this bucket was created outside of Terraform
terraform {
  backend "s3" {
    profile = "yangmillstheory"
    bucket  = "yangmillstheory-terraform-states"
    region  = "us-west-2"
    key     = "budget.tfstate"
  }
}

variable "bucket" {
  default = "yangmillstheory-budget"
}

variable "s3_email_prefix" {
  default = "email"
}

variable "csv_key" {
  default = "budget.csv"
}

variable "csv_template_key" {
  default = "budget.csv.tmpl"
}

# S3 bucket for entire application
resource "aws_s3_bucket" "app" {
  bucket = "${var.bucket}"
}

data "aws_iam_policy_document" "ses_to_s3" {
  statement {
    sid = "1"

    actions = [
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.app.arn}/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["ses.amazonaws.com"]
    }
  }

  statement {
    sid = "2"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.app.arn}/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_s3_bucket_policy" "app_bucket" {
  bucket = "${aws_s3_bucket.app.id}"
  policy = "${data.aws_iam_policy_document.ses_to_s3.json}"
}

resource "aws_s3_bucket_object" "csv_template" {
  bucket = "${var.bucket}"
  key    = "${var.csv_template_key}"
  source = "${var.csv_key}"
  etag   = "${md5(file("${var.csv_key}"))}"

  lifecycle {
    ignore_changes = ["*"]
  }
}

resource "aws_s3_bucket_object" "csv" {
  bucket = "${var.bucket}"
  key    = "${var.csv_key}"
  source = "${var.csv_key}"
  etag   = "${md5(file("${var.csv_key}"))}"

  lifecycle {
    ignore_changes = ["*"]
  }
}

# comes from shell environment
variable "budget_email" {}
variable "allowed_senders" {}
variable "max_period_spend" {
  default = "250"
}

# lambda email receiver
module "email_receiver" {
  bucket           = "${var.bucket}"
  source           = "./email-receiver"
  csv_bucket       = "${var.bucket}"
  csv_key          = "${var.csv_key}"
  key              = "email_receiver.zip"
  email_bucket     = "${var.bucket}"
  email_prefix     = "${var.s3_email_prefix}"
  sns_topic_arn    = "${module.notify.ok_arn}"
  alarm_arn        = "${module.notify.error_arn}"
  allowed_senders  = "${var.allowed_senders}"
  max_period_spend = "${var.max_period_spend}"
}

# lambda budget reset
module "budget_reset" {
  bucket           = "${var.bucket}"
  source           = "./reset"
  csv_bucket       = "${var.bucket}"
  csv_key          = "${var.csv_key}"
  csv_template_key = "${var.csv_template_key}"
  key              = "budget_reset.zip"
  sns_topic_arn    = "${module.notify.reset_arn}"
  alarm_arn        = "${module.notify.error_arn}"
  max_period_spend = "${var.max_period_spend}"
}

# SES receipt rule to store email in S3 and invoke Lambda
variable "budget_rule_set_name" {
  default = "budget-tracking"
}

resource "aws_ses_receipt_rule" "update_budget" {
  name          = "update_budget"
  rule_set_name = "${var.budget_rule_set_name}"

  recipients = [
    "${var.budget_email}",
  ]

  enabled      = true
  scan_enabled = true
  tls_policy   = "Require"

  s3_action {
    bucket_name       = "${var.bucket}"
    object_key_prefix = "${var.s3_email_prefix}"
    position          = 1
  }

  lambda_action {
    function_arn    = "${module.email_receiver.lambda_arn}"
    invocation_type = "Event"
    position        = 2
  }

  depends_on = [
    "module.email_receiver",
    "aws_s3_bucket_policy.app_bucket",
  ]
}

resource "aws_ses_receipt_rule_set" "budget_tracking" {
  rule_set_name = "${var.budget_rule_set_name}"
}

resource "aws_ses_active_receipt_rule_set" "budget_tracking" {
  rule_set_name = "${var.budget_rule_set_name}"
  depends_on    = ["aws_ses_receipt_rule_set.budget_tracking"]
}

# SNS budget-related topics
module "notify" {
  source = "./notify"
}
