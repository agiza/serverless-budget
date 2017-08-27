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

resource "aws_s3_bucket" "budget" {
  bucket = "yangmillstheory-budget"
}

variable "budget_rule_set_name" {
  default = "budget-tracking"
}

resource "aws_ses_receipt_rule" "store" {
  name          = "store"
  rule_set_name = "${var.budget_rule_set_name}"
  recipients    = ["budget@yangmillstheory.com"]
  enabled       = true
  scan_enabled  = true
}

resource "aws_ses_active_receipt_rule_set" "budget_tracking" {
  rule_set_name = "${var.budget_rule_set_name}"
}
