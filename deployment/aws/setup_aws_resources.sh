#!/usr/bin/env bash
# ==============================================================================
# AWS Cloud Infrastructure Setup Script (AWS CLI)
# Aqua OS Platform: Automated Provisioning of Security Groups, IAM Roles & S3
# Prerequisites: AWS CLI v2 configured with Administrator/PowerUser credentials
# ==============================================================================
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-1}"
SG_NAME="aqua-ec2-sg"
IAM_ROLE_NAME="AquaEC2InstanceRole"
IAM_PROFILE_NAME="AquaEC2InstanceProfile"

echo "=========================================================="
echo " Starting Aqua OS AWS Cloud Resource Provisioning         "
echo " AWS Region: ${AWS_REGION}                                "
echo " Date:       $(date -u +"%Y-%m-%dT%H:%M:%SZ")             "
echo "=========================================================="

# 0. Get AWS Account ID
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query "Account" --output text)"
BACKUP_BUCKET="aqua-backups-${AWS_ACCOUNT_ID}-${AWS_REGION}"
echo "--> AWS Account: ${AWS_ACCOUNT_ID}"
echo "--> Target Backup Bucket: ${BACKUP_BUCKET}"

# 1. Query Default VPC ID
echo "--> Querying default VPC..."
VPC_ID="$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --region "${AWS_REGION}" --query "Vpcs[0].VpcId" --output text)"
if [ -z "${VPC_ID}" ] || [ "${VPC_ID}" = "None" ]; then
  echo "[-] Default VPC not found. Querying first available VPC..."
  VPC_ID="$(aws ec2 describe-vpcs --region "${AWS_REGION}" --query "Vpcs[0].VpcId" --output text)"
fi
echo "    Found VPC ID: ${VPC_ID}"

# 2. Create Security Group
echo "--> Setting up Security Group '${SG_NAME}'..."
SG_ID="$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" --region "${AWS_REGION}" --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || true)"

if [ -z "${SG_ID}" ] || [ "${SG_ID}" = "None" ]; then
  SG_ID="$(aws ec2 create-security-group \
    --group-name "${SG_NAME}" \
    --description "Aqua OS EC2 Graviton Security Group (Inbound 80, 443, 8080, 1883, 1884)" \
    --vpc-id "${VPC_ID}" \
    --region "${AWS_REGION}" \
    --query "GroupId" --output text)"
  echo "    Created Security Group: ${SG_ID}"
else
  echo "    Security Group already exists: ${SG_ID}"
fi

# Add Inbound Rules
echo "--> Authorizing Inbound Rules on ${SG_ID}..."
RULES=(
  "tcp 80 0.0.0.0/0 HTTP_Ingress"
  "tcp 443 0.0.0.0/0 HTTPS_Ingress"
  "tcp 8080 0.0.0.0/0 Dev_API_Ingress"
  "tcp 1883 0.0.0.0/0 Production_MQTT"
  "tcp 1884 0.0.0.0/0 Development_MQTT"
  "tcp 22 0.0.0.0/0 SSH_Management"
)

for RULE in "${RULES[@]}"; do
  read -r PROTO PORT CIDR DESC <<< "${RULE}"
  aws ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" \
    --protocol "${PROTO}" \
    --port "${PORT}" \
    --cidr "${CIDR}" \
    --region "${AWS_REGION}" 2>/dev/null || true
done
echo "    Security Group rules updated (Direct Postgres/Redis ports 5432/6379 are blocked)."

# 3. Create IAM Role for EC2 (AWS Systems Manager + S3 Backups)
echo "--> Setting up IAM Role '${IAM_ROLE_NAME}'..."
TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}'

aws iam create-role \
  --role-name "${IAM_ROLE_NAME}" \
  --assume-role-policy-document "${TRUST_POLICY}" \
  --description "Role for Aqua OS EC2 Graviton with SSM and S3 backup permissions" 2>/dev/null || true

# Attach AWS SSM Managed Policy (for zero-trust browser CLI without open SSH keys)
aws iam attach-role-policy \
  --role-name "${IAM_ROLE_NAME}" \
  --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"

# S3 Backup Access Policy
S3_BACKUP_POLICY=$(cat << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::${BACKUP_BUCKET}",
        "arn:aws:s3:::${BACKUP_BUCKET}/*"
      ]
    }
  ]
}
EOF
)

aws iam put-role-policy \
  --role-name "${IAM_ROLE_NAME}" \
  --policy-name "AquaS3BackupPolicy" \
  --policy-document "${S3_BACKUP_POLICY}"

# Create IAM Instance Profile
echo "--> Creating IAM Instance Profile '${IAM_PROFILE_NAME}'..."
aws iam create-instance-profile --instance-profile-name "${IAM_PROFILE_NAME}" 2>/dev/null || true
aws iam add-role-to-instance-profile \
  --instance-profile-name "${IAM_PROFILE_NAME}" \
  --role-name "${IAM_ROLE_NAME}" 2>/dev/null || true

# 4. Create Private S3 Bucket for Database Backups
echo "--> Provisioning S3 Backup Bucket '${BACKUP_BUCKET}'..."
if [ "${AWS_REGION}" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "${BACKUP_BUCKET}" --region "${AWS_REGION}" 2>/dev/null || true
else
  aws s3api create-bucket --bucket "${BACKUP_BUCKET}" \
    --region "${AWS_REGION}" \
    --create-bucket-configuration LocationConstraint="${AWS_REGION}" 2>/dev/null || true
fi

# Enable default server-side encryption (AES256)
aws s3api put-bucket-encryption \
  --bucket "${BACKUP_BUCKET}" \
  --server-side-encryption-configuration '{
    "Rules": [{ "ApplyServerSideEncryptionByDefault": { "SSEAlgorithm": "AES256" } }]
  }' 2>/dev/null || true

# Block All Public Access to backups
aws s3api put-public-access-block \
  --bucket "${BACKUP_BUCKET}" \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" 2>/dev/null || true

# S3 Lifecycle Rule: Transition to Glacier after 30 days, expire after 90 days
LIFECYCLE_CONFIG='{
  "Rules": [
    {
      "ID": "AquaArchiveAndCleanup",
      "Filter": { "Prefix": "backups/" },
      "Status": "Enabled",
      "Transitions": [
        { "Days": 30, "StorageClass": "GLACIER" }
      ],
      "Expiration": { "Days": 90 }
    }
  ]
}'
aws s3api put-bucket-lifecycle-configuration \
  --bucket "${BACKUP_BUCKET}" \
  --lifecycle-configuration "${LIFECYCLE_CONFIG}" 2>/dev/null || true

echo "=========================================================="
echo " AWS Cloud Resources Provisioned Successfully!             "
echo " Security Group ID:        ${SG_ID}                       "
echo " IAM Instance Profile:     ${IAM_PROFILE_NAME}           "
echo " Encrypted Backup Bucket:  ${BACKUP_BUCKET}               "
echo "=========================================================="
echo ""
echo "--> To launch the EC2 Graviton Instance, run:"
echo "aws ec2 run-instances \\"
echo "  --image-id resolve:ssm:/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id \\"
echo "  --instance-type t4g.medium \\"
echo "  --iam-instance-profile Name=${IAM_PROFILE_NAME} \\"
echo "  --security-group-ids ${SG_ID} \\"
echo "  --block-device-mappings '[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":40,\"VolumeType\":\"gp3\",\"Encrypted\":true}}]' \\"
echo "  --user-data file://deployment/aws/bootstrap_ec2.sh \\"
echo "  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=aqua-graviton-host}]' \\"
echo "  --region ${AWS_REGION}"
