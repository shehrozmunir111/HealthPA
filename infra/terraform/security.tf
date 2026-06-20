# ── Security group for the EC2 app host ──────────────────────────────
resource "aws_security_group" "app" {
  name        = "${var.project_prefix}-app-sg"
  description = "HealthPA app host: web + restricted SSH"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH (locked to your IP)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_prefix}-app-sg" }
}

# ── Security group for RDS: only the app host may reach Postgres ──────
resource "aws_security_group" "db" {
  name        = "${var.project_prefix}-db-sg"
  description = "HealthPA Postgres: only from app SG"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from app host only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_prefix}-db-sg" }
}
