# note that SMS topic subscriptions are unsupported in Terraform, so
# those are not included in this module.
#
#   https://www.terraform.io/docs/providers/aws/r/sns_topic_subscription.html
output "ok_arn" {
  value = "${aws_sns_topic.budget_update_ok.arn}"
}

output "error_arn" {
  value = "${aws_sns_topic.budget_update_error.arn}"
}

resource "aws_sns_topic" "budget_update_ok" {
  name         = "budget-update-ok"
  display_name = "Budget Update Success"
}

resource "aws_sns_topic" "budget_update_error" {
  name         = "budget-update-error"
  display_name = "Budget Update Error"
}

data "aws_iam_policy_document" "sns_publish" {
  statement {
    sid = "1"

    actions = [
      "sns:Publish",
    ]

    resources = [
      "${aws_sns_topic.budget_update_ok.arn}",
    ]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_sns_topic_policy" "sns_publish" {
  arn    = "${aws_sns_topic.budget_update_ok.arn}"
  policy = "${data.aws_iam_policy_document.sns_publish.json}"
}
