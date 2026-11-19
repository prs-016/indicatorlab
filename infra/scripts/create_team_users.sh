#!/usr/bin/env bash
# Create IAM logins for teammates and add them to the indicatorlab-team group.
# Run it yourself, signed in as your own IAM user (never root). Each new one-time password is printed
# once, to this terminal only: send it to that person privately (a DM), never in the group chat.
#
#   infra/scripts/create_team_users.sh             # jamal jack james
#   infra/scripts/create_team_users.sh prakhar     # anyone else later
set -euo pipefail
GROUP="${TEAM_GROUP:-indicatorlab-team}"
USERS=("$@")
[[ ${#USERS[@]} -gt 0 ]] || USERS=(jamal jack james)

CALLER="$(aws sts get-caller-identity --query Arn --output text)"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
if [[ "$CALLER" == *":root" ]]; then
  echo "You are signed in as root. Sign in as your own IAM user first (the guide: never the root account)." >&2
  exit 1
fi
aws iam get-group --group-name "$GROUP" >/dev/null 2>&1 \
  || { echo "Group $GROUP not found: deploy the shared stack first (infra/shared/deploy.sh)." >&2; exit 1; }

echo "Sign-in URL: https://$ACCOUNT.signin.aws.amazon.com/console"
for u in "${USERS[@]}"; do
  if aws iam get-user --user-name "$u" >/dev/null 2>&1; then
    echo "exists   $u (password left unchanged)"
  else
    aws iam create-user --user-name "$u" --tags Key=project,Value=indicatorlab >/dev/null
    # 16 random characters plus one of each class, so any default password policy accepts it
    pw="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-16)Aa1!"
    aws iam create-login-profile --user-name "$u" --password "$pw" --password-reset-required >/dev/null
    echo "created  $u   one-time password: $pw"
  fi
  aws iam add-user-to-group --user-name "$u" --group-name "$GROUP"
done
echo "Each person signs in at the URL above with their username, sets a new password, then creates"
echo "their own access key (IAM > Users > <name> > Security credentials) for 'aws configure'."
