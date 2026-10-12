terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  # Terraform refuses to plan or apply against any other account, so a stray default
  # credential (another account's, say) can never be deployed into by accident.
  allowed_account_ids = [var.account_id]

  default_tags {
    tags = {
      Project   = var.name
      ManagedBy = "terraform"
    }
  }
}
