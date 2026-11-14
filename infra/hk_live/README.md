# Optional HK live deployment handoff

Prepared locally. **Not deployed or tested against a real AWS account.**
The user retained a local-only scope. No credentials, images or cloud resources
were created, and no team message was sent.

The CloudFormation template provisions a 0.25-vCPU/1-GB ARM64 Fargate service,
HK quote table, receipt watchdog, weekday HK-time start/stop schedules and an
alarm. It reuses the team's existing `indicatorlab-data` S3 bucket and existing
public subnets; no NAT Gateway or public inbound API is created. The service
starts at 09:20 HKT, stops at 16:10 HKT and pauses during lunch/holidays in code.
Schedules use Asia/Hong_Kong, so Pacific daylight-saving changes do not move them.

The separate watchdog checks receipt times every minute, applies the XHKG
calendar, and publishes healthy during lunch, holidays and outside sessions.
There is a one-minute opening/reopening grace. Its absence also alarms; a
crashed quote worker cannot suppress the alarm by failing to emit a heartbeat.
This monitors ingestion time, not whether a quiet stock traded in the last minute.

Before deployment, coordinate ownership of the table with Joshua. If it already
exists outside this stack, import/reference it rather than attempt duplicate
creation. The template retains the table on deletion. The image and network
parameters must be real team values, and the current dated roster needs
maintenance after index reviews. The optional SNS parameter uses an existing
topic; no email subscriptions are created.

Build and push the Docker image from the repository root using your team's
authenticated ECR workflow. Both ECS and Lambda use the same ARM64 image;
the collector overrides the Lambda image entry point. Then, in an authorized
team us-west-2 profile, deployment is one command:

```bash
aws cloudformation deploy --region us-west-2 --stack-name indicatorlab-hk-live \
  --template-file infra/hk_live/template.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides ImageUri=YOUR_ECR_IMAGE_URI VpcId=YOUR_VPC_ID PublicSubnets=YOUR_SUBNET_IDS
```

No deployment has been executed. To stop paid collection, set this ECS service's
desired count to zero **and disable the Start schedule**. Verify actual costs
against the team's $20 budget before and after deployment. Do not delete the
shared bucket or retained quote table as a routine rollback.

After deployment, prove during a real HKEX session that all 95 DynamoDB records
update about every five seconds, S3 minute keys arrive, lunch/holiday suppression
works, and James's `/live/hk` reads the agreed seven fields. Those external
acceptance checks cannot be claimed by local template/tests.

Primary references: [EventBridge universal targets](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html),
[CloudFormation ECS service](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecs-service.html),
[Scheduler timezones](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-scheduler-schedule.html).
