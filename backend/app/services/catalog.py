"""The Cloud Service Provider (CSP) catalog.

This is the single source of truth for:
  * which clouds / categories / services the agent and UI know about, and
  * the folder path an ADR for a given service is filed under.

Folder layout produced:  adrs/<cloud>/<category-path>/<service-slug>/
e.g.                     adrs/gcp/database/warehouse/bigquery/
                         adrs/aws/database/sql/postgresql/
                         adrs/azure/storage/blob/

Extend this file to add services; the UI and agent pick up changes automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Service:
    slug: str            # folder + id-friendly, e.g. "gcs"
    name: str            # display name, e.g. "Cloud Storage (GCS) Bucket"
    category: str        # top-level category slug, e.g. "storage"
    subpath: str = ""    # optional nested path under the category, e.g. "sql"
    aliases: tuple[str, ...] = ()   # extra terms the agent can match on

    @property
    def folder(self) -> str:
        """Relative folder path (POSIX-style) under the cloud root."""
        parts = [self.category]
        if self.subpath:
            parts.append(self.subpath)
        parts.append(self.slug)
        return "/".join(parts)


@dataclass(frozen=True)
class Cloud:
    slug: str
    name: str
    services: list[Service] = field(default_factory=list)


# Human-friendly labels for top-level categories (used by the UI).
CATEGORY_LABELS = {
    "compute": "Compute",
    "storage": "Storage",
    "database": "Database",
    "networking": "Networking",
    "security-identity": "Security & Identity",
    "containers": "Containers",
    "serverless": "Serverless",
    "analytics": "Analytics & Big Data",
    "messaging": "Messaging & Streaming",
    "monitoring": "Monitoring & Ops",
    "ai-ml": "AI / ML",
    "developer-tools": "Developer Tools",
    "management": "Management & Governance",
    "other": "Other",
}

# The canonical category slugs the agent may file an ad-hoc service under.
CATEGORIES = list(CATEGORY_LABELS.keys())


def normalize_category(category: str | None) -> str:
    """Coerce a free-form category to a known slug, defaulting to 'other'."""
    if not category:
        return "other"
    c = category.strip().lower().replace(" ", "-").replace("_", "-")
    if c in CATEGORY_LABELS:
        return c
    # light aliasing for common phrasings
    aliases = {
        "security": "security-identity", "identity": "security-identity",
        "iam": "security-identity", "db": "database", "data": "analytics",
        "bigdata": "analytics", "big-data": "analytics", "ml": "ai-ml",
        "ai": "ai-ml", "genai": "ai-ml", "network": "networking",
        "container": "containers", "queue": "messaging", "streaming": "messaging",
        "storage-bucket": "storage", "vm": "compute", "function": "serverless",
    }
    return aliases.get(c, "other")


def build_folder(category: str, subpath: str, service_slug: str) -> str:
    """Folder path (POSIX) under the cloud root for an ad-hoc (non-catalog) service."""
    parts = [normalize_category(category)]
    sub = (subpath or "").strip().strip("/")
    if sub:
        parts.append(sub)
    parts.append(service_slug)
    return "/".join(parts)


def _catalog() -> list[Cloud]:
    aws = Cloud("aws", "Amazon Web Services", [
        # compute
        Service("ec2", "EC2 Instance", "compute", aliases=("virtual machine", "vm")),
        Service("lambda", "Lambda Function", "serverless", aliases=("function",)),
        Service("ecs", "ECS Cluster", "containers"),
        Service("eks", "EKS (Kubernetes) Cluster", "containers", aliases=("k8s", "kubernetes")),
        # storage
        Service("s3", "S3 Bucket", "storage", aliases=("object storage", "bucket")),
        Service("efs", "EFS File System", "storage", "file"),
        # database
        Service("mysql", "RDS for MySQL", "database", "sql", aliases=("rds mysql",)),
        Service("postgresql", "RDS for PostgreSQL", "database", "sql", aliases=("rds postgres", "postgres")),
        Service("aurora", "Aurora", "database", "sql"),
        Service("dynamodb", "DynamoDB Table", "database", "nosql", aliases=("nosql",)),
        Service("redshift", "Redshift Warehouse", "database", "warehouse", aliases=("data warehouse",)),
        # networking
        Service("vpc", "VPC", "networking", aliases=("virtual private cloud",)),
        Service("alb", "Application Load Balancer", "networking", aliases=("load balancer",)),
        Service("cloudfront", "CloudFront CDN", "networking", aliases=("cdn",)),
        # security & identity
        Service("iam", "IAM Role / Policy", "security-identity", aliases=("role", "policy")),
        Service("kms", "KMS Key", "security-identity", aliases=("encryption key",)),
        Service("secrets-manager", "Secrets Manager", "security-identity", aliases=("secret",)),
        # analytics / messaging / monitoring
        Service("glue", "Glue ETL Job", "analytics"),
        Service("athena", "Athena", "analytics"),
        Service("sqs", "SQS Queue", "messaging", aliases=("queue",)),
        Service("sns", "SNS Topic", "messaging", aliases=("topic", "pubsub")),
        Service("kinesis", "Kinesis Stream", "messaging", "streaming"),
        Service("cloudwatch", "CloudWatch", "monitoring", aliases=("logs", "metrics")),
    ])

    gcp = Cloud("gcp", "Google Cloud Platform", [
        Service("gce", "Compute Engine VM", "compute", aliases=("virtual machine", "vm")),
        Service("cloud-functions", "Cloud Functions", "serverless", aliases=("function",)),
        Service("cloud-run", "Cloud Run", "serverless", aliases=("container run",)),
        Service("gke", "GKE (Kubernetes) Cluster", "containers", aliases=("k8s", "kubernetes")),
        Service("gcs", "Cloud Storage (GCS) Bucket", "storage", aliases=("bucket", "object storage", "gcs bucket")),
        Service("filestore", "Filestore", "storage", "file"),
        Service("cloud-sql-mysql", "Cloud SQL for MySQL", "database", "sql", aliases=("cloud sql mysql",)),
        Service("cloud-sql-postgresql", "Cloud SQL for PostgreSQL", "database", "sql", aliases=("cloud sql postgres", "postgres")),
        Service("spanner", "Cloud Spanner", "database", "sql"),
        Service("firestore", "Firestore", "database", "nosql", aliases=("nosql",)),
        Service("bigtable", "Bigtable", "database", "nosql"),
        Service("bigquery", "BigQuery Dataset", "database", "warehouse", aliases=("data warehouse", "bq")),
        Service("vpc", "VPC Network", "networking", aliases=("virtual private cloud",)),
        Service("load-balancer", "Cloud Load Balancing", "networking", aliases=("load balancer",)),
        Service("cloud-cdn", "Cloud CDN", "networking", aliases=("cdn",)),
        Service("iam", "IAM Role / Policy", "security-identity", aliases=("role", "policy")),
        Service("kms", "Cloud KMS Key", "security-identity", aliases=("encryption key",)),
        Service("secret-manager", "Secret Manager", "security-identity", aliases=("secret",)),
        Service("dataflow", "Dataflow", "analytics"),
        Service("dataproc", "Dataproc", "analytics"),
        Service("pubsub", "Pub/Sub Topic", "messaging", aliases=("topic", "queue")),
        Service("cloud-monitoring", "Cloud Monitoring", "monitoring", aliases=("logs", "metrics")),
    ])

    azure = Cloud("azure", "Microsoft Azure", [
        Service("vm", "Virtual Machine", "compute", aliases=("virtual machine",)),
        Service("functions", "Azure Functions", "serverless", aliases=("function",)),
        Service("container-apps", "Container Apps", "serverless"),
        Service("aks", "AKS (Kubernetes) Cluster", "containers", aliases=("k8s", "kubernetes")),
        Service("blob", "Blob Storage", "storage", aliases=("bucket", "object storage")),
        Service("files", "Azure Files", "storage", "file"),
        Service("azure-sql", "Azure SQL Database", "database", "sql", aliases=("sql server",)),
        Service("mysql", "Azure Database for MySQL", "database", "sql"),
        Service("postgresql", "Azure Database for PostgreSQL", "database", "sql", aliases=("postgres",)),
        Service("cosmos-db", "Cosmos DB", "database", "nosql", aliases=("nosql",)),
        Service("synapse", "Synapse Analytics", "database", "warehouse", aliases=("data warehouse",)),
        Service("vnet", "Virtual Network", "networking", aliases=("vpc",)),
        Service("app-gateway", "Application Gateway", "networking", aliases=("load balancer",)),
        Service("front-door", "Front Door CDN", "networking", aliases=("cdn",)),
        Service("entra-id", "Entra ID Role / Identity", "security-identity", aliases=("azure ad", "iam", "role")),
        Service("key-vault", "Key Vault", "security-identity", aliases=("secret", "encryption key")),
        Service("data-factory", "Data Factory", "analytics"),
        Service("service-bus", "Service Bus", "messaging", aliases=("queue", "topic")),
        Service("event-hubs", "Event Hubs", "messaging", "streaming"),
        Service("monitor", "Azure Monitor", "monitoring", aliases=("logs", "metrics")),
    ])

    return [aws, gcp, azure]


CLOUDS: list[Cloud] = _catalog()
CLOUD_BY_SLUG: dict[str, Cloud] = {c.slug: c for c in CLOUDS}


def find_service(cloud_slug: str, service_slug: str) -> Service | None:
    cloud = CLOUD_BY_SLUG.get(cloud_slug)
    if not cloud:
        return None
    return next((s for s in cloud.services if s.slug == service_slug), None)


def search(query: str, cloud_slug: str | None = None) -> list[tuple[str, Service]]:
    """Fuzzy-ish search by name/slug/alias, ranked most-relevant first.

    Scoring rewards whole-query hits and matches against the service slug/name over
    matches that only hit a generic alias, so "gcs bucket" surfaces GCS ahead of S3.
    """
    q = query.lower().strip()
    # Cloud-name words act as a filter, not a service match term, so "azure blob"
    # doesn't score every Azure service just for containing "azure".
    cloud_keywords = {
        "aws": "aws", "amazon": "aws",
        "gcp": "gcp", "google": "gcp",
        "azure": "azure", "microsoft": "azure",
    }
    words = [w for w in q.split() if w]
    inferred_cloud = next((cloud_keywords[w] for w in words if w in cloud_keywords), None)
    words = [w for w in words if w not in cloud_keywords]
    q = " ".join(words)
    cloud_slug = cloud_slug if cloud_slug in CLOUD_BY_SLUG else inferred_cloud
    scored: list[tuple[int, str, Service]] = []
    clouds = [CLOUD_BY_SLUG[cloud_slug]] if cloud_slug in CLOUD_BY_SLUG else CLOUDS
    for cloud in clouds:
        for svc in cloud.services:
            name = svc.name.lower()
            haystack = " ".join([name, svc.slug, *svc.aliases])
            score = 0
            if q and q in haystack:
                score += 5
            if q and (q in name or q in svc.slug):
                score += 6
            for w in words:
                if w in svc.slug or w in name.split():
                    score += 3
                elif w in haystack:
                    score += 1
            if score:
                scored.append((score, cloud.slug, svc))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [(cslug, svc) for _, cslug, svc in scored]


def catalog_as_dict() -> list[dict]:
    """Serializable catalog for the API / UI."""
    out = []
    for cloud in CLOUDS:
        cats: dict[str, list[dict]] = {}
        for svc in cloud.services:
            cats.setdefault(svc.category, []).append({
                "slug": svc.slug,
                "name": svc.name,
                "subpath": svc.subpath,
                "folder": svc.folder,
                "aliases": list(svc.aliases),
            })
        out.append({
            "slug": cloud.slug,
            "name": cloud.name,
            "categories": [
                {
                    "slug": cat,
                    "label": CATEGORY_LABELS.get(cat, cat.title()),
                    "services": svcs,
                }
                for cat, svcs in sorted(cats.items())
            ],
        })
    return out
