import boto3

REGION = "us-west-2"
ENDPOINT = "hotel-release-endpoint"

cloudwatch = boto3.client("cloudwatch", region_name=REGION)

dimensions = [
    {"Name": "EndpointName", "Value": ENDPOINT},
    {"Name": "VariantName", "Value": "AllTraffic"}
]

cloudwatch.put_metric_alarm(
    AlarmName="hotel-release-errors",
    Namespace="AWS/SageMaker",
    MetricName="Invocation5XXErrors",
    Dimensions=dimensions,
    Statistic="Sum",
    Period=60,
    EvaluationPeriods=1,
    Threshold=1,
    ComparisonOperator="GreaterThanOrEqualToThreshold",
    TreatMissingData="notBreaching"
)

cloudwatch.put_metric_alarm(
    AlarmName="hotel-release-latency",
    Namespace="AWS/SageMaker",
    MetricName="ModelLatency",
    Dimensions=dimensions,
    Statistic="Average",
    Period=60,
    EvaluationPeriods=2,
    Threshold=500000,
    ComparisonOperator="GreaterThanThreshold",
    TreatMissingData="notBreaching"
)

print("Both CloudWatch alarms created successfully.")