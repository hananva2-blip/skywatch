terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = "eu-west-1"
}

# 1. ברירת המחדל של ה-VPC
resource "aws_default_vpc" "default" {
  tags = {
    Name = "Default VPC"
  }
}

# 2. איתור דינמי של Ubuntu 22.04 LTS AMI העדכני
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# 3. Security Group
resource "aws_security_group" "skywatch_sg" {
  name        = "skywatch-sg"
  description = "Security group for SkyWatch K3s cluster"
  vpc_id      = aws_default_vpc.default.id

  # SSH
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # K3s API Server
  ingress {
    description = "K3s API Server"
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # NodePort טווח שירותים
  ingress {
    description = "Kubernetes NodePort services"
    from_port   = 30000
    to_port     = 32767
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Intra-cluster תקשורת חופשית בין שרתי הקלאסטר
  ingress {
    description = "Intra-cluster internal traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "skywatch-sg"
  }
}

# 4. הגדרת שרתי ה-EC2
locals {
  instances = {
    master   = "skywatch-master"
    worker1  = "skywatch-worker"
    worker2  = "skywatch-worker2"
  }
}

resource "aws_instance" "nodes" {
  for_each               = local.instances
  ami                    = data.aws_ami.ubuntu.id
  instance_type = each.key == "master" ? "t3.small" : "t3.micro"
  key_name               = "skywatch-key"
  vpc_security_group_ids = [aws_security_group.skywatch_sg.id]

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = {
    Name = each.value
    Role = each.key
  }
}

# 5. יצירה אוטומטית של קובץ Ansible Inventory
resource "local_file" "ansible_inventory" {
  content = templatefile("${path.module}/inventory.tmpl", {
    master_public_ip   = aws_instance.nodes["master"].public_ip
    master_private_ip  = aws_instance.nodes["master"].private_ip
    worker1_public_ip  = aws_instance.nodes["worker1"].public_ip
    worker1_private_ip = aws_instance.nodes["worker1"].private_ip
    worker2_public_ip  = aws_instance.nodes["worker2"].public_ip
    worker2_private_ip = aws_instance.nodes["worker2"].private_ip
  })
  filename = "${path.module}/../ansible/inventory.ini"
}

# 6. Outputs
output "master_public_ip" {
  value = aws_instance.nodes["master"].public_ip
}

output "worker1_public_ip" {
  value = aws_instance.nodes["worker1"].public_ip
}

output "worker2_public_ip" {
  value = aws_instance.nodes["worker2"].public_ip
}
