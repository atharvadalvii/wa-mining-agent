variable "account_id" {
  description = "The only AWS account Terraform may act on."
  type        = string
  default     = "322122798516"
}

variable "aws_profile" {
  description = "AWS CLI profile to use (must belong to var.account_id). Null uses the default credential chain."
  type        = string
  default     = null
}

variable "region" {
  description = "Sydney is the closest region to Western Australia."
  type        = string
  default     = "ap-southeast-2"
}

variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "wa-mining-agent"
}

variable "cpu" {
  description = "Fargate task CPU units (1024 = 1 vCPU)."
  type        = number
  default     = 1024
}

variable "memory" {
  description = "Fargate task memory in MiB. Measured ~2.9 GiB with only the driving data loaded; 8 GiB leaves room for walking data and large isochrone graphs."
  type        = number
  default     = 8192
}

variable "desired_count" {
  description = "Number of running tasks. Starts at 0 so the first apply doesn't try to run a container before the image, data and secret exist; set to 1 once they do."
  type        = number
  default     = 0
}

variable "max_session_messages" {
  description = "Questions allowed per visitor session (protects the model bill)."
  type        = number
  default     = 30
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget; an email is sent at 80% of actual spend and when the forecast exceeds 100%."
  type        = number
  default     = 60
}

variable "alert_email" {
  description = "Email address for budget alerts."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository (owner/name) allowed to deploy via OIDC."
  type        = string
  default     = "atharvadalvii/wa-mining-agent"
}

variable "create_github_oidc_provider" {
  description = "Create the account's GitHub OIDC provider. Set false if one already exists (only one is allowed per account)."
  type        = bool
  default     = true
}
