variable "bucket" {
  type = "string"
}

variable "key" {
  type = "string"
}

variable "csv_bucket" {
  type = "string"
}

variable "csv_key" {
  type = "string"
}

variable "csv_template_key" {
  type = "string"
}

variable "sns_topic_arn" {
  type = "string"
}

variable "alarm_arn" {
  type = "string"
}

variable "max_period_spend" {
  type    = "string"
  default = "250"
}

variable "lambda_name" {
  default = "budget-reset"
}

output "lambda_arn" {
  value = "${aws_lambda_function.budget_reset.arn}"
}

data "terraform_remote_state" "lambda" {
  backend = "s3"

  config {
    profile = "yangmillstheory"
    bucket  = "yangmillstheory-terraform-states"
    region  = "us-west-2"
    key     = "lambda.tfstate"
  }
}

resource "aws_sqs_queue" "budget_reset_deadletter" {
  name = "budget_reset_deadletter"
}

resource "aws_sqs_queue_policy" "lambda_to_deadletter" {
  queue_url = "${aws_sqs_queue.budget_reset_deadletter.id}"

  policy = <<POLICY
{
  "Version": "2012-10-17",
  "Id": "sqspolicy",
  "Statement": [
    {
      "Sid": "First",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "sqs:SendMessage",
      "Resource": "${aws_sqs_queue.budget_reset_deadletter.arn}",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "${aws_sqs_queue.budget_reset_deadletter.arn}"
        }
      }
    }
  ]
}
POLICY
}

resource "aws_cloudwatch_metric_alarm" "deadletter_queue_alarm" {
  alarm_name          = "Budget reset failed!"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 120
  statistic           = "Sum"
  threshold           = 0

  dimensions = {
    QueueName = "${aws_sqs_queue.budget_reset_deadletter.name}"
  }

  alarm_description         = "Triggers when number of messsages is greater than zero."
  alarm_actions             = ["${var.alarm_arn}"]
  ok_actions                = ["${var.alarm_arn}"]
  insufficient_data_actions = ["${var.alarm_arn}"]

  treat_missing_data = "notBreaching"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "reset/lambda.py"
  output_path = "reset/lambda.zip"
}

# annoying issue here: https://github.com/hashicorp/terraform/issues/15594
resource "aws_s3_bucket_object" "lambda" {
  bucket = "${var.bucket}"
  key    = "${var.key}"
  source = "${data.archive_file.lambda_zip.output_path}"
  etag   = "${data.archive_file.lambda_zip.output_base64sha256}"
}

resource "aws_lambda_function" "budget_reset" {
  function_name     = "${var.lambda_name}"
  s3_bucket         = "${var.bucket}"
  s3_key            = "${var.key}"
  s3_object_version = "${aws_s3_bucket_object.lambda.version_id}"

  dead_letter_config {
    target_arn = "${aws_sqs_queue.budget_reset_deadletter.arn}"
  }

  environment {
    variables = {
      csv_bucket       = "${var.csv_bucket}"
      csv_key          = "${var.csv_key}"
      csv_template_key = "${var.csv_template_key}"
      sns_topic_arn    = "${var.sns_topic_arn}"
      max_period_spend = "${var.max_period_spend}"
    }
  }

  runtime          = "python3.6"
  role             = "${data.terraform_remote_state.lambda.basic_execution_role_arn}"
  handler          = "lambda.handler"
  source_code_hash = "${data.archive_file.lambda_zip.output_base64sha256}"

  timeout = 300
}

# note that I still had to manually enable the trigger. this isn't good.
#
# https://us-west-2.console.aws.amazon.com/lambda/home?region=us-west-2#/functions/budget-reset?tab=triggers
resource "aws_lambda_permission" "allow_cloudwatch_invoke" {
  statement_id  = "AllowInvokeFromCloudWatch"
  principal     = "events.amazonaws.com"
  action        = "lambda:InvokeFunction"
  function_name = "${var.lambda_name}"
  source_arn    = "${aws_cloudwatch_event_rule.every_monday_7am_pst.arn}"

  depends_on = [
    "aws_lambda_function.budget_reset"
  ]
}

resource "aws_cloudwatch_event_rule" "every_monday_7am_pst" {
  name                = "every-monday-7am-pst"
  description         = "Every Monday at 7AM PST"
  schedule_expression = "cron(0 14 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "budget_reset" {
  rule = "${aws_cloudwatch_event_rule.every_monday_7am_pst.name}"
  arn  = "${aws_lambda_function.budget_reset.arn}"
}

