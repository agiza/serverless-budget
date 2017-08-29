variable "bucket" {
  type = "string"
}

variable "key" {
  type = "string"
}

variable "api_key_s3_path" {
  type = "string"
}

variable "sns_topic_arn" {
  type = "string"
}

variable "alarm_arn" {
  type = "string"
}

variable "lambda_name" {
  default = "email-receiver"
}

output "lambda_arn" {
  value = "${aws_lambda_function.email_receiver.arn}"
}

output "lambda_name" {
  value = "${var.lambda_name}"
}

resource "aws_sqs_queue" "email_receiver_deadletter" {
  name = "email_receiver_deadletter"
}

resource "aws_cloudwatch_metric_alarm" "deadletter_queue_alarm" {
  alarm_name          = "Budget update failed!"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 120
  statistic           = "Sum"
  threshold           = 0

  dimensions = {
    QueueName = "${aws_sqs_queue.email_receiver_deadletter.name}"
  }

  alarm_description         = "Triggers when number of messsages is greater than zero."
  alarm_actions             = ["${var.alarm_arn}"]
  ok_actions                = ["${var.alarm_arn}"]
  insufficient_data_actions = ["${var.alarm_arn}"]

  treat_missing_data = "notBreaching"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "email-receiver/lambda.py"
  output_path = "email-receiver/lambda.zip"
}

resource "aws_s3_bucket_object" "lambda" {
  bucket = "${var.bucket}"
  key    = "${var.key}"
  source = "${data.archive_file.lambda_zip.output_path}"
  etag   = "${data.archive_file.lambda_zip.output_base64sha256}"
}

resource "aws_lambda_function" "email_receiver" {
  function_name     = "${var.lambda_name}"
  s3_bucket         = "${var.bucket}"
  s3_key            = "${var.key}"
  s3_object_version = "${aws_s3_bucket_object.lambda.version_id}"

  dead_letter_config {
    target_arn = "${aws_sqs_queue.email_receiver_deadletter.arn}"
  }

  environment {
    variables = {
      api_key_s3_path = "${var.api_key_s3_path}"
      sns_topic_arn   = "${var.sns_topic_arn}"
    }
  }

  runtime          = "python3.6"
  role             = "${aws_iam_role.lambda_basic_execution.arn}"
  handler          = "lambda.handler"
  source_code_hash = "${data.archive_file.lambda_zip.output_base64sha256}"

  timeout = 300
}
