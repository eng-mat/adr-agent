---
id: ADR-0001
title: Standardization of GCP Dataflow Pipelines for Batch and Streaming Workloads
status: Accepted
date: 2026-07-19
author: Cloud Engineering
cloud: Google Cloud Platform
service: Dataflow
category: analytics
tags: []
---

# ADR-0001: Standardization of GCP Dataflow Pipelines for Batch and Streaming Workloads

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-19 |
| **Author** | Cloud Engineering |
| **Cloud** | Google Cloud Platform |
| **Service** | Dataflow |
| **Category** | analytics |

## Context

The organization requires a unified, scalable, and secure data processing framework to handle both batch and streaming data pipelines across all environments (dev, qa, preprod, prod, and dr). These pipelines must ingest from and write to various sources and sinks (such as Pub/Sub, BigQuery, Cloud Storage, and Cloud Spanner) while adhering to strict enterprise security, network isolation, and encryption compliance standards.

## Decision

We will standardize on Google Cloud Dataflow as the serverless data processing engine for both batch and streaming Apache Beam pipelines. All Dataflow jobs will run in private-only network mode (no public IPs on workers) with Private Google Access enabled. All pipeline data at rest (including temporary shuffle storage, state storage, and persistent disks) will be encrypted using Customer-Managed Encryption Keys (CMEK) via Cloud KMS. Pipelines will be deployed via Terraform and run under dedicated, least-privilege Service Accounts using Workload Identity where applicable.

## Architecture & Configuration

### 1. Deployment Model
- **Engine:** Serverless Apache Beam execution via Google Cloud Dataflow.
- **Environments:** Standardized configurations across `dev`, `qa`, `preprod`, `prod`, and `dr`.
- **Execution Types:** Supports both **Batch** and **Streaming** pipelines using Java, Python, or Go SDKs.

### 2. Network Isolation
- **Private Workers:** All Dataflow workers must be provisioned without public IP addresses (`ip_configuration = "WORKER_IP_PRIVATE"`).
- **VPC Subnet:** Workers must run in a dedicated private subnet with **Private Google Access** enabled.
- **Firewall Rules:** Ingress and egress traffic must be restricted to the minimum required for worker-to-worker communication (TCP ports 12345-12346) and communication with GCP APIs.
- **VPC Service Controls (VPC-SC):** Integration within the organization's security perimeter to prevent data exfiltration.

### 3. Sizing & Autoscaling
- **Streaming Engine:** Must be enabled (`enable_streaming_engine = true`) to offload windowing and state storage from worker VMs, improving scaling responsiveness.
- **Autoscaling Limits:**
  - **Dev/QA:** `max_workers = 5`, worker type `n2-standard-2`.
  - **Preprod/Prod/DR:** `max_workers = 100` (or as justified by workload volume), worker type `n2-standard-4` or memory-optimized instances as required.
- **Flex Templates:** Standardize on **Dataflow Flex Templates** packaged as Docker images in Artifact Registry for consistent deployment across environments.

### 4. Storage & State Management
- **Staging & Temp Buckets:** Dedicated Cloud Storage buckets for staging (`staging_gcs_location`) and temporary data (`temp_gcs_location`).
- **Bucket Policies:** Enforce **Public Access Prevention** and **Uniform Bucket-Level Access** on all associated GCS buckets.
- **Retention:** Staging and temp buckets must have GCS lifecycle rules to delete objects older than 7 days.

## Security & Compliance

### 1. Encryption
- **At Rest:** Mandatory Customer-Managed Encryption Keys (CMEK) via Cloud KMS for all temporary storage, shuffle storage, and persistent disks used by workers.
- **In Transit:** TLS 1.2+ enforced for all internal and external communications.

### 2. Identity & Access Management (IAM)
- **Dedicated Service Account:** Each pipeline must run under its own dedicated Service Account (e.g., `org-<env>-<app>-df-sa@<project>.iam.gserviceaccount.com`).
- **Least Privilege:** Service Accounts must only be granted the minimum required permissions:
  - `roles/dataflow.worker` (required for worker execution).
  - Specific reader/writer roles for sources/sinks (e.g., `roles/pubsub.subscriber`, `roles/bigquery.dataEditor`, `roles/storage.objectViewer`).
  - **No primitive roles** (`roles/owner`, `roles/editor`) are permitted.

### 3. Network Posture
- **Private Google Access:** Subnet must have Private Google Access enabled to allow workers to communicate with GCP APIs without public IPs.
- **No Public IPs:** Workers must not have external IP addresses assigned.

### 4. Logging & Monitoring
- **Audit Logs:** Cloud Audit Logs (Admin Activity and Data Access) must be enabled.
- **Job Logs:** All pipeline execution logs, system logs, and worker logs must be automatically shipped to Cloud Logging and Cloud Monitoring.

> Security guidance is derived from the organization's Cloud Security Standard.
> See references below. Replace placeholder links with your Confluence pages.

## Standards & Naming Conventions

### 1. Naming Conventions
- **Dataflow Job:** `org-<env>-<app>-df-<pipeline-name>`
- **KMS Key:** `org-<env>-<app>-df-key`
- **GCS Staging Bucket:** `org-<env>-<app>-df-staging-gcs`
- **Service Account:** `org-<env>-<app>-df-sa`

*Where `<env>` is one of: `dev`, `qa`, `preprod`, `prod`, `dr`.*

### 2. Mandatory Labels
All resources (Dataflow jobs, GCS buckets, KMS keys) must be tagged with the following labels:
- `owner`: `<team-name>`
- `cost-center`: `<billing-code>`
- `data-classification`: `confidential` (or `restricted` depending on data type)
- `environment`: `dev` | `qa` | `preprod` | `prod` | `dr`
- `app`: `<application-name>`
- `managed-by`: `terraform`

## Consequences

**Positive**
- Fully serverless execution eliminates the operational overhead of cluster management and scaling.
- Unified programming model (Apache Beam) simplifies development for both batch and streaming pipelines.
- Strict network isolation and mandatory CMEK encryption satisfy stringent enterprise compliance requirements.
- Streaming Engine offloads state storage, improving performance and scaling speed.

**Negative / Trade-offs**
- Vendor lock-in to the Google Cloud Dataflow runner (though Apache Beam code remains portable).
- Cold start times during worker provisioning can introduce startup latency for batch jobs.
- Distributed execution makes debugging and log correlation more complex than single-node systems.

## Alternatives Considered

1. **Self-hosted Apache Spark on Dataproc:** Rejected due to the operational overhead of managing, sizing, and scaling clusters. Dataflow offers a fully serverless, zero-ops execution model for Apache Beam pipelines.
2. **Google Cloud Run / Cloud Functions:** Rejected for large-scale batch and complex streaming windowing operations, as they lack the distributed processing, shuffle capabilities, and autoscaling efficiency required for high-throughput pipelines.

## Infrastructure as Code (Automation Hint)

resource "google_dataflow_flex_template_job" "dataflow_job" {
  provider                = google-beta
  name                    = "org-${var.environment}-${var.app}-df-pipeline"
  container_spec_gcs_path = "gs://${google_storage_bucket.staging.name}/templates/pipeline-template.json"
  
  parameters = {
    inputSubscription = "projects/${var.project_id}/subscriptions/org-${var.environment}-${var.app}-sub"
    outputTable       = "${var.project_id}:${google_bigquery_table.output.dataset_id}.${google_bigquery_table.output.table_id}"
  }

  # Network & Security Settings
  sdk_container_image = "${var.region}-docker.pkg.dev/${var.project_id}/dataflow-templates/pipeline:latest"
  service_account_email = google_service_account.dataflow_sa.email
  network               = var.vpc_network_self_link
  subnetwork            = var.subnet_self_link
  ip_configuration      = "WORKER_IP_PRIVATE"
  kms_key_name          = var.kms_key_arn

  # Performance & Scaling
  max_workers           = var.max_workers
  enable_streaming_engine = true

  labels = {
    owner               = var.owner
    cost-center         = var.cost_center
    data-classification = var.data_classification
    environment         = var.environment
    app                 = var.app
    managed-by          = "terraform"
  }
}

## Automation Notes

- The Terraform configuration must explicitly set `ip_configuration = "WORKER_IP_PRIVATE"`.
- The Dataflow Service Agent (`service-<project-number>@dataflow-service-producer-prod.iam.gserviceaccount.com`) and the Compute Engine Service Agent must be granted the `roles/cloudkms.cryptoKeyEncrypterDecrypter` role on the CMEK key before job submission.
- Ensure the dedicated pipeline Service Account has `roles/dataflow.worker` and the necessary read/write permissions for the specific sources/sinks (e.g., `roles/pubsub.subscriber`, `roles/bigquery.dataEditor`).

## References

- GCP Security Baseline (gcp/security/gcp-security-baseline.md)
- Cloud Architecture Standard (global/architecture/cloud-architecture-standard.md)
- Google Cloud Dataflow Security Documentation
