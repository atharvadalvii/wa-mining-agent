resource "aws_lb" "app" {
  name               = var.name
  load_balancer_type = "application"
  subnets            = data.aws_subnets.default.ids
  security_groups    = [aws_security_group.alb.id]

  # Streamlit holds a websocket per visitor; keep idle ones open past the default 60 s.
  idle_timeout = 300
}

resource "aws_lb_target_group" "app" {
  name        = var.name
  port        = 8501
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = data.aws_vpc.default.id

  health_check {
    path                = "/_stcore/health"
    matcher             = "200"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }

  # A visitor's session state lives in one task, so keep each visitor on the same one
  # if the service is ever scaled past a single task.
  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400
    enabled         = true
  }

  deregistration_delay = 30
}

# HTTP only: HTTPS needs a domain name and an ACM certificate. Add an
# aws_lb_listener on 443 and redirect this one once you have a domain.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
