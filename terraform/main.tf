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
