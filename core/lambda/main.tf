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
    key     = "lambda.tfstate"
  }
}

output "basic_execution_role_arn" {
  value = "${aws_iam_role.lambda_basic_execution.arn}"
}

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

    resources = ["arn:aws:sns:us-west-2:079529114411:*"]
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

data "aws_iam_policy_document" "lambda_to_s3" {
  statement {
    sid = "1"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = ["arn:aws:s3:::*"]
  }
}

resource "aws_iam_policy" "lambda_to_s3" {
  name   = "lambda-to-s3"
  policy = "${data.aws_iam_policy_document.lambda_to_s3.json}"
}

resource "aws_iam_policy_attachment" "lambda_to_s3" {
  roles = [
    "${aws_iam_role.lambda_basic_execution.name}",
  ]

  name       = "lambda-to-s3"
  policy_arn = "${aws_iam_policy.lambda_to_s3.arn}"
}

data "aws_iam_policy_document" "sqs_publish" {
  statement {
    sid = "1"

    actions = [
      "sqs:SendMessage",
    ]

    resources = ["arn:aws:sqs:us-west-2:079529114411:*"]
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
