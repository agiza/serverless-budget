data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_basic_execution" {
  name               = "lambda-basic-execution"
  assume_role_policy = "${data.aws_iam_policy_document.lambda_assume_role.json}"
}

resource "aws_iam_policy_attachment" "lambda_to_cloudwatch" {
  roles = [
    "${aws_iam_role.lambda_basic_execution.name}",
  ]

  name       = "lambda-to-cloudwatch"
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "sns_publish" {
  statement {
    sid = "1"

    actions = [
      "sns:Publish",
    ]

    resources = ["${var.sns_topic_arn}"]
  }
}

resource "aws_iam_policy" "sns_publish" {
  name   = "sns-publish"
  policy = "${data.aws_iam_policy_document.sns_publish.json}"
}

resource "aws_iam_policy_attachment" "lambda_to_sns" {
  roles = [
    "${aws_iam_role.lambda_basic_execution.name}",
  ]

  name       = "lambda-to-sns"
  policy_arn = "${aws_iam_policy.sns_publish.arn}"
}

data "aws_iam_policy_document" "s3_get_object" {
  statement {
    sid = "1"

    actions = [
      "s3:GetObject",
    ]

    resources = ["arn:aws:s3:::*"]
  }
}

resource "aws_iam_policy" "s3_get_object" {
  name   = "s3-get-object"
  policy = "${data.aws_iam_policy_document.s3_get_object.json}"
}

resource "aws_iam_policy_attachment" "lambda_to_s3" {
  roles = [
    "${aws_iam_role.lambda_basic_execution.name}",
  ]

  name       = "lambda-to-s3"
  policy_arn = "${aws_iam_policy.s3_get_object.arn}"
}

data "aws_iam_policy_document" "sqs_publish" {
  statement {
    sid = "1"

    actions = [
      "sqs:SendMessage",
    ]

    resources = ["${aws_sqs_queue.email_receiver_deadletter.arn}"]
  }
}

resource "aws_iam_policy" "sqs_publish" {
  name   = "sqs-publish"
  policy = "${data.aws_iam_policy_document.sqs_publish.json}"
}

resource "aws_iam_policy_attachment" "lambda_to_sqs" {
  roles = [
    "${aws_iam_role.lambda_basic_execution.name}",
  ]

  name       = "lambda-to-sqs"
  policy_arn = "${aws_iam_policy.sqs_publish.arn}"
}

resource "aws_sqs_queue_policy" "lambda_to_deadletter" {
  queue_url = "${aws_sqs_queue.email_receiver_deadletter.id}"
  policy    = "${data.aws_iam_policy_document.sqs_publish.json}"
}

resource "aws_lambda_permission" "ses_invoke" {
  function_name = "${var.lambda_name}"
  action        = "lambda:InvokeFunction"
  principal     = "ses.amazonaws.com"
  statement_id  = "AllowInvokeFromSES"

  depends_on = [
    "aws_lambda_function.email_receiver",
  ]
}
