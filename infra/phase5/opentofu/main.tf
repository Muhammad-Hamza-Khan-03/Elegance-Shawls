# Draft only: not initialised, planned or applied. Credentials come from the environment
# (CLOUDFLARE_API_TOKEN), never from this file.
terraform {
  required_providers {
    cloudflare = { source = "cloudflare/cloudflare" }
  }
}

variable "account_id" { type = string }
variable "zone_id" { type = string }
variable "vps_ip" { type = string }

resource "cloudflare_record" "shop" {
  zone_id = var.zone_id
  name    = "shop"
  type    = "A"
  content = var.vps_ip
  proxied = true
}

resource "cloudflare_r2_bucket" "backups" {
  account_id = var.account_id
  name       = "elegance-backups"
}
