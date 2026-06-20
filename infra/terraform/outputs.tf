output "app_public_ip" {
  description = "Elastic IP of the app host. Point your domain's A record here."
  value       = aws_eip.app.public_ip
}

output "app_url" {
  description = "Where HealthPA is reachable."
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${aws_eip.app.public_ip}"
}

output "expense_url" {
  description = "Where expense-forecasting is reachable (second app, port 8080)."
  value       = "http://${aws_eip.app.public_ip}:8080"
}

output "ssh_command" {
  description = "SSH in (replace the .pem path)."
  value       = "ssh -i <your-key>.pem ec2-user@${aws_eip.app.public_ip}"
}

output "rds_endpoint" {
  description = "Private RDS endpoint (reachable only from the app host)."
  value       = aws_db_instance.main.address
}

output "uploads_bucket" {
  value = aws_s3_bucket.uploads.bucket
}

output "ssm_env_parameter" {
  description = "Where the production .env lives. Edit it, then redeploy on the host."
  value       = aws_ssm_parameter.env.name
}
