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
    key     = "ses.tfstate"
  }
}

data "terraform_remote_state" "route53" {
  backend = "s3"

  config {
    profile = "yangmillstheory"
    bucket  = "yangmillstheory-terraform-states"
    region  = "us-west-2"
    key     = "route53.tfstate"
  }
}

# allow SES to receive emails on our behalf, see
#
#   http://docs.aws.amazon.com/ses/latest/DeveloperGuide/receiving-email.html
#
# FIXME this was done in the console
#
resource "aws_ses_domain_identity" "domain" {
  domain = "${data.terraform_remote_state.route53.primary_zone_name}"
}

resource "aws_route53_record" "text_verify" {
  zone_id = "${data.terraform_remote_state.route53.primary_zone_id}"
  name    = "_amazonses.yangmillstheory.com"
  type    = "TXT"
  ttl     = "1800"

  records = [
    # FIXME: this was done in the console
    "eOtNsI8wkBwxuyhiHUtEeGHvDHCZb6gLeHL0kPPHQMA=",

    "${aws_ses_domain_identity.domain.verification_token}",
  ]
}

resource "aws_route53_record" "receive_email" {
  zone_id = "${data.terraform_remote_state.route53.primary_zone_id}"
  name    = "${data.terraform_remote_state.route53.primary_zone_name}"
  type    = "MX"
  ttl     = "1800"

  records = [
    "10 inbound-smtp.us-east-1.amazonaws.com",
  ]
}
