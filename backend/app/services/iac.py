"""Infrastructure-as-Code hints for ADRs.

Produces a per-cloud, per-service scaffolding hint (Terraform resource/module + CLI +
key inputs) that the automation team can start from. Works for catalog services and for
ad-hoc services the agent invents on request — unknown services get a correct, generic
per-cloud hint rather than nothing.
"""
from __future__ import annotations

# Per-cloud tooling defaults.
CLOUD_IAC = {
    "aws": {
        "provider": "hashicorp/aws",
        "cli": "aws",
        "module_registry": "registry.terraform.io/terraform-aws-modules",
        "docs": "https://registry.terraform.io/providers/hashicorp/aws/latest/docs",
    },
    "gcp": {
        "provider": "hashicorp/google",
        "cli": "gcloud",
        "module_registry": "registry.terraform.io/terraform-google-modules",
        "docs": "https://registry.terraform.io/providers/hashicorp/google/latest/docs",
    },
    "azure": {
        "provider": "hashicorp/azurerm",
        "cli": "az",
        "module_registry": "registry.terraform.io/Azure",
        "docs": "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs",
    },
}

# Well-known service -> primary Terraform resource(s). Keyed by "cloud/service_slug".
SERVICE_RESOURCES: dict[str, list[str]] = {
    # AWS
    "aws/s3": ["aws_s3_bucket", "aws_s3_bucket_public_access_block", "aws_s3_bucket_server_side_encryption_configuration"],
    "aws/ec2": ["aws_instance"],
    "aws/lambda": ["aws_lambda_function", "aws_iam_role"],
    "aws/ecs": ["aws_ecs_cluster", "aws_ecs_service"],
    "aws/eks": ["aws_eks_cluster", "aws_eks_node_group"],
    "aws/mysql": ["aws_db_instance"],
    "aws/postgresql": ["aws_db_instance"],
    "aws/aurora": ["aws_rds_cluster", "aws_rds_cluster_instance"],
    "aws/dynamodb": ["aws_dynamodb_table"],
    "aws/redshift": ["aws_redshift_cluster"],
    "aws/vpc": ["aws_vpc", "aws_subnet"],
    "aws/kms": ["aws_kms_key", "aws_kms_alias"],
    "aws/iam": ["aws_iam_role", "aws_iam_policy"],
    "aws/secrets-manager": ["aws_secretsmanager_secret"],
    "aws/sqs": ["aws_sqs_queue"],
    "aws/sns": ["aws_sns_topic"],
    # GCP
    "gcp/gcs": ["google_storage_bucket", "google_storage_bucket_iam_binding"],
    "gcp/gce": ["google_compute_instance"],
    "gcp/cloud-functions": ["google_cloudfunctions2_function"],
    "gcp/cloud-run": ["google_cloud_run_v2_service"],
    "gcp/gke": ["google_container_cluster", "google_container_node_pool"],
    "gcp/cloud-sql-mysql": ["google_sql_database_instance", "google_sql_database"],
    "gcp/cloud-sql-postgresql": ["google_sql_database_instance", "google_sql_database"],
    "gcp/spanner": ["google_spanner_instance", "google_spanner_database"],
    "gcp/firestore": ["google_firestore_database"],
    "gcp/bigtable": ["google_bigtable_instance"],
    "gcp/bigquery": ["google_bigquery_dataset", "google_bigquery_table"],
    "gcp/vpc": ["google_compute_network", "google_compute_subnetwork"],
    "gcp/kms": ["google_kms_key_ring", "google_kms_crypto_key"],
    "gcp/iam": ["google_project_iam_custom_role", "google_project_iam_binding"],
    "gcp/secret-manager": ["google_secret_manager_secret"],
    "gcp/pubsub": ["google_pubsub_topic", "google_pubsub_subscription"],
    # Azure
    "azure/blob": ["azurerm_storage_account", "azurerm_storage_container"],
    "azure/vm": ["azurerm_linux_virtual_machine"],
    "azure/functions": ["azurerm_linux_function_app"],
    "azure/aks": ["azurerm_kubernetes_cluster"],
    "azure/azure-sql": ["azurerm_mssql_server", "azurerm_mssql_database"],
    "azure/mysql": ["azurerm_mysql_flexible_server"],
    "azure/postgresql": ["azurerm_postgresql_flexible_server"],
    "azure/cosmos-db": ["azurerm_cosmosdb_account"],
    "azure/synapse": ["azurerm_synapse_workspace"],
    "azure/vnet": ["azurerm_virtual_network", "azurerm_subnet"],
    "azure/key-vault": ["azurerm_key_vault", "azurerm_key_vault_key"],
    "azure/entra-id": ["azuread_application", "azuread_service_principal"],
    "azure/service-bus": ["azurerm_servicebus_namespace", "azurerm_servicebus_queue"],
}

# Sensible key inputs to prompt the automation team, by category.
CATEGORY_INPUTS: dict[str, list[str]] = {
    "storage": ["name", "location/region", "encryption key (CMEK)", "versioning", "lifecycle rules", "public access block"],
    "database": ["engine version", "instance size/tier", "storage size", "private networking", "backup/retention", "CMEK", "HA/replicas"],
    "compute": ["machine type/size", "image", "network/subnet", "disk encryption", "IAM/instance role", "tags"],
    "containers": ["node size & count", "k8s version", "private cluster", "network policy", "workload identity/OIDC"],
    "serverless": ["runtime", "memory/timeout", "trigger", "identity/role", "env vars via secret manager"],
    "networking": ["CIDR ranges", "subnets/zones", "firewall/security-group rules", "private endpoints", "flow logs"],
    "security-identity": ["scope", "least-privilege actions", "rotation policy", "key spec/protection level"],
    "analytics": ["dataset/job config", "source/sink", "service account/role", "encryption", "network access"],
    "messaging": ["throughput/partitions", "retention", "encryption", "access policy", "DLQ"],
    "monitoring": ["metrics/log sources", "retention", "alert routes", "sink/workspace"],
}

DEFAULT_INPUTS = ["name", "region/location", "encryption (CMEK)", "network access", "IAM/least-privilege", "mandatory tags"]


def iac_hint_markdown(
    *, cloud_slug: str, service_slug: str, service_name: str, category: str
) -> str:
    cloud = CLOUD_IAC.get(cloud_slug)
    if not cloud:
        return "_No IaC hint available for this cloud._"

    key = f"{cloud_slug}/{service_slug}"
    resources = SERVICE_RESOURCES.get(key)
    inputs = CATEGORY_INPUTS.get(category, DEFAULT_INPUTS)

    # Each element is its own Markdown block; join with blank lines so paragraphs and the
    # bullet list render cleanly (no lazy-continuation merging).
    blocks = [f"**Tooling:** Terraform (`{cloud['provider']}`) · CLI `{cloud['cli']}`"]
    if resources:
        res_list = ", ".join(f"`{r}`" for r in resources)
        blocks.append(f"**Primary Terraform resource(s):** {res_list}")
    else:
        blocks.append(
            f"**Terraform resource:** look up the resource for _{service_name}_ in the "
            f"[{cloud_slug} provider docs]({cloud['docs']}) "
            f"(no pinned mapping — treat as a new service)."
        )
    blocks.append(f"**Suggested module namespace:** `{cloud['module_registry']}`")
    bullets = "\n".join(f"- {i}" for i in inputs)
    blocks.append(
        "**Key inputs the automation team should parameterize:**\n\n" + bullets
    )
    blocks.append(
        "**Guardrails to encode:** private access by default, CMEK encryption, "
        "least-privilege IAM, audit logging, and the mandatory tag set."
    )
    return "\n\n".join(blocks)
