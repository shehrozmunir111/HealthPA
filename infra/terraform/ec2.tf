# Latest Amazon Linux 2023 AMI (Docker-friendly, has SSM agent preinstalled).
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_eip" "app" {
  domain = "vpc"
  tags   = { Name = "${var.project_prefix}-eip" }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  key_name               = var.ec2_key_name

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    project_prefix = var.project_prefix
    aws_region     = var.aws_region
    git_repo_url   = var.git_repo_url
    git_branch     = var.git_branch
    ssm_env_name   = aws_ssm_parameter.env.name
  })

  # Re-run user_data if the bootstrap script changes (forces replace).
  user_data_replace_on_change = true

  tags = { Name = "${var.project_prefix}-app" }

  depends_on = [aws_db_instance.main]
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}
