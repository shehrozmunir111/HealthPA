terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # ── Remote state (recommended once you go past day 1) ──────────────
  # Create an S3 bucket + DynamoDB table once, then uncomment this block
  # so your state is shared and locked (essential for teams / CI).
  #
  # backend "s3" {
  #   bucket         = "healthpa-tfstate-<your-unique-suffix>"
  #   key            = "healthpa/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "healthpa-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "HealthPA"
      ManagedBy = "Terraform"
      Env       = var.environment
    }
  }
}
