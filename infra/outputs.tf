output "app_url" {
  description = "Public URL (HTTP) once the service is running."
  value       = "http://${aws_lb.app.dns_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "data_bucket" {
  description = "Upload the offline street data under s3://<this>/data/ (see README)."
  value       = aws_s3_bucket.data.id
}

output "maps_bucket" {
  value = aws_s3_bucket.maps.id
}

output "openai_secret_arn" {
  description = "Put the OpenAI key here with `aws secretsmanager put-secret-value`."
  value       = aws_secretsmanager_secret.openai.arn
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN secret in the GitHub repo."
  value       = aws_iam_role.github_deploy.arn
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service" {
  value = aws_ecs_service.app.name
}
