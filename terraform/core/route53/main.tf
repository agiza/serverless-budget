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
    key     = "route53.tfstate"
  }
}

variable "primary_zone_id" {
  default = "Z1XVQJ2173I5AH"
}

variable "primary_zone_name" {
  default = "yangmillstheory.com"
}

# these zone attributes were created when registering yangmillstheory.com, and zones aren't importable
#
# note that registration creates an SOA and an NS record, both of which should not be modified!
output "primary_zone_id" {
  value = "${var.primary_zone_id}"
}

output "primary_zone_name" {
  value = "yangmillstheory.com"
}

resource "aws_route53_record" "soa" {
  zone_id = "${var.primary_zone_id}"
  name    = "${var.primary_zone_name}"
  type    = "SOA"
  ttl     = "900"

  records = [
    "ns-1048.awsdns-03.org. awsdns-hostmaster.amazon.com. 1 7200 900 1209600 86400",
  ]
}

resource "aws_route53_record" "nameservers" {
  zone_id = "${var.primary_zone_id}"
  name    = "${var.primary_zone_name}"
  type    = "NS"
  ttl     = "172800"

  records = [
    "ns-1048.awsdns-03.org.",
    "ns-557.awsdns-05.net.",
    "ns-212.awsdns-26.com.",
    "ns-1738.awsdns-25.co.uk.",
  ]
}
