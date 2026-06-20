# EC2 instance role: lets the app use SES, read its secrets from SSM,
# and read/write the uploads bucket — WITHOUT any static AWS keys in .env.
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${var.project_prefix}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

data "aws_iam_policy_document" "app_permissions" {
  # Send transactional email through SES
  statement {
    sid       = "SES"
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = ["*"]
  }

  # Read the app's .env from SSM Parameter Store (SecureString)
  statement {
    sid       = "SSMRead"
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:parameter/${var.project_prefix}/*"]
  }

  # Decrypt the SecureString (default AWS-managed SSM key)
  statement {
    sid       = "KMSDecrypt"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
  }

  # OCR uploads bucket
  statement {
    sid     = "S3Uploads"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.uploads.arn,
      "${aws_s3_bucket.uploads.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "app" {
  name   = "${var.project_prefix}-app-policy"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.app_permissions.json
}

# Lets you open a shell via SSM Session Manager (no SSH key needed)
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_prefix}-ec2-profile"
  role = aws_iam_role.ec2.name
}
