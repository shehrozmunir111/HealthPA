resource "aws_db_subnet_group" "main" {
  name       = "${var.project_prefix}-db-subnets"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${var.project_prefix}-db-subnets" }
}

resource "aws_db_instance" "main" {
  identifier     = "${var.project_prefix}-db"
  engine         = "postgres"
  engine_version = "15"

  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 0 # disable autoscaling so you can't accidentally exceed free tier
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false # single-AZ keeps it in the free tier

  backup_retention_period = 7
  skip_final_snapshot     = true # set false for real prod
  deletion_protection     = false

  tags = { Name = "${var.project_prefix}-db" }
}
