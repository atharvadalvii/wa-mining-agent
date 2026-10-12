# Offline WA street network (parquet tables + the .pbf), downloaded by the container at start.
resource "aws_s3_bucket" "data" {
  bucket_prefix = "${var.name}-data-"
}

# Map exports published for visitors via presigned links.
resource "aws_s3_bucket" "maps" {
  bucket_prefix = "${var.name}-maps-"
}

resource "aws_s3_bucket_public_access_block" "private" {
  for_each = {
    data = aws_s3_bucket.data.id
    maps = aws_s3_bucket.maps.id
  }

  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "private" {
  for_each = {
    data = aws_s3_bucket.data.id
    maps = aws_s3_bucket.maps.id
  }

  bucket = each.value

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Presigned map links last 6 hours, so objects older than a day are just clutter.
resource "aws_s3_bucket_lifecycle_configuration" "maps" {
  bucket = aws_s3_bucket.maps.id

  rule {
    id     = "expire-maps"
    status = "Enabled"

    filter {}

    expiration {
      days = 1
    }
  }
}

resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# The OpenAI key lives here, never in the repo, the image or Terraform state: only the
# empty secret is created. Put the value in with `aws secretsmanager put-secret-value`.
resource "aws_secretsmanager_secret" "openai" {
  name_prefix             = "${var.name}/openai-api-key-"
  description             = "OpenAI API key for ${var.name}"
  recovery_window_in_days = 7
}
