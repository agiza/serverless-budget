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

module "budget_update" {
  source = "./budget-update"
}

data "aws_iam_policy_document" "sns_publish" {
  statement {
    sid = "1"

    actions = [
      "sns:Publish",
    ]

    resources = [
      "${module.budget_update.ok_arn}",
    ]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
  }
}

variable "bucket" {
  default = "yangmillstheory-budget"
}

variable "s3_email_prefix" {
  default = "email"
}

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

resource "aws_sns_topic_policy" "sns_publish" {
  arn    = "${module.budget_update.ok_arn}"
  policy = "${data.aws_iam_policy_document.sns_publish.json}"
}

module "email_receiver" {
  bucket          = "${var.bucket}"
  source          = "./email-receiver"
  api_key_s3_path = "api_key_s3_path_placeholder"
  key             = "email_receiver.zip"
  email_bucket    = "${var.bucket}"
  email_prefix    = "${var.s3_email_prefix}"
  sns_topic_arn   = "${module.budget_update.ok_arn}"
  alarm_arn       = "${module.budget_update.error_arn}"
}

#########################
# set up SES receipt rule
variable "budget_rule_set_name" {
  default = "budget-tracking"
}

variable "budget_email" {
  default = "budget@yangmillstheory.com"
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
