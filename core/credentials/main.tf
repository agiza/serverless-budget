# TODO move this out into a separate repo?
provider "aws" {
  region  = "${var.region}"
  profile = "${var.profile}"
}

terraform {
  backend "s3" {
    profile = "yangmillstheory"
    bucket  = "yangmillstheory-terraform-states"
    region  = "us-west-2"
    key     = "credentials.tfstate"
  }
}

variable "bucket" {
  default = "yangmillstheory-credentials"
}

output "google_api_key_s3_path" {
  value = "${var.bucket}/${aws_s3_bucket_object.google_api_key.id}"
}

resource "aws_s3_bucket" "credentials" {
  bucket = "${var.bucket}"
}

data "aws_iam_policy_document" "lambda_read" {
  statement {
    sid = "1"

    actions = [
      "s3:GetObject",
    ]

    resources = [
      "${aws_s3_bucket.credentials.arn}/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_s3_bucket_policy" "credentials_bucket" {
  bucket = "${aws_s3_bucket.credentials.id}"
  policy = "${data.aws_iam_policy_document.lambda_read.json}"
}

resource "aws_s3_bucket_object" "google_api_key" {
  bucket = "${var.bucket}"
  source = "google-api-key.cred"
  key    = "google-api-key"
  etag   = "${md5(file("google-api-key.cred"))}"
}
