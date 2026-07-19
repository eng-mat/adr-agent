# Deploying the ADR Agent to Cloud Run (Shared VPC, internal, CMEK)

Run these commands **one after another, top to bottom**. Every command uses literal values —
no shell variables, no scripts. To reuse this in another organization, find-and-replace the
values in the table below.

## How the work is split

| | Where | What |
|---|---|---|
| **Host project** | `my-host-project` | Networking is **already in place**. You only *verify* things and grant IAM — nothing is created here. |
| **Service project** | `my-service-project` | Everything you create: KMS, Artifact Registry, GCS, Secret Manager, service accounts, Cloud Run, and all load balancer components. |
| **Cloud Build** | service project | **Builds and pushes the image only.** It has no `run.admin` and cannot deploy. |
| **Cloud Run deploy** | you, manually | §9 |

Assumptions confirmed for this environment:
- Zscaler egress **routes and firewall rules already exist** — you only attach the network tag.
- A **proxy-only subnet already exists** in the region — do not create another.
- **DNS is handled by the org's self-service portal** (§11), exactly as for GKE: reserve a
  static IP, map a custom name to it, submit. No Cloud DNS zone or record is created.
- The hostname is a **private-only name** (e.g. `myapp.adr.agent`), not a public domain — so
  the certificate must come from the **internal CA** (§10a).

---

## Values to find-and-replace

| Placeholder | Meaning |
|---|---|
| `my-host-project` | Shared VPC **host** project ID (networking lives here) |
| `my-service-project` | **Service** project ID (workload lives here) |
| `222222222222` | **Service** project number — `gcloud projects describe my-service-project --format='value(projectNumber)'` |
| `us-central1` | Region (must match the existing subnet and KMS) |
| `my-vpc` | Shared VPC network name (in the host project) |
| `my-existing-subnet` | Existing app subnet (in the host project) |
| `zscaler-egress` | Existing network tag that routes egress to Zscaler — **confirm the real one in §7c** |
| `10.0.0.0/8` | On-prem CIDR allowed to reach the LB |
| `myapp.adr.agent` | Internal FQDN |

Point gcloud at the service project (host-project commands pass `--project` explicitly):

```bash
gcloud config set project my-service-project
```

---

## Target architecture

```
 on-prem laptop
      │  self-service DNS: myapp.adr.agent → LB VIP (private)
      │  Interconnect / VPN
      ▼
 ┌─ host project: my-host-project ──────────────┐
 │  Shared VPC "my-vpc"                         │
 │   • my-existing-subnet   (shared)            │
 │   • proxy-only subnet    (exists)            │
 │   • Zscaler routes + firewall (exist)        │
 └───────────────────┬──────────────────────────┘
                     │ subnets shared to
 ┌─ service project: my-service-project ────────┐
 │  Internal Application LB (HTTPS :443)        │
 │            │ serverless NEG                  │
 │            ▼                                 │
 │  Cloud Run (INTERNAL ingress, no public URL) │
 │   • CMEK · GCS volume (CMEK) · Secret Mgr    │
 │            │ egress tag: zscaler-egress      │
 │            ▼ existing route → Zscaler → GitHub
 └──────────────────────────────────────────────┘
```

---

## 1. Enable APIs (service project)

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudkms.googleapis.com \
  secretmanager.googleapis.com \
  compute.googleapis.com \
  dns.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com
```

Check org policies that commonly block this (do this first in a new org):

```bash
gcloud resource-manager org-policies list --project=my-service-project
```

Watch for `constraints/run.allowedIngress`, `constraints/gcp.restrictNonCmekServices`,
`constraints/compute.restrictSharedVpcSubnetworks`.

---

## 2. KMS — one CMEK key (service project)

The key must be in the **same region** as the resources it protects.

```bash
gcloud kms keyrings create adr-agent-ring --location=us-central1
```

```bash
gcloud kms keys create adr-agent-key \
  --location=us-central1 \
  --keyring=adr-agent-ring \
  --purpose=encryption \
  --rotation-period=90d \
  --next-rotation-time=2026-10-17T00:00:00Z
```

### Grant each Google service agent use of the key

CMEK is applied by **service agents**, not your own service accounts. A missing grant here is
the single most common cause of deploy failures.

Create the service identities first (no-ops if they exist):

```bash
gcloud beta services identity create --service=artifactregistry.googleapis.com --project=my-service-project
```

```bash
gcloud beta services identity create --service=secretmanager.googleapis.com --project=my-service-project
```

Cloud Run:

```bash
gcloud kms keys add-iam-policy-binding adr-agent-key \
  --location=us-central1 --keyring=adr-agent-ring \
  --member=serviceAccount:service-222222222222@serverless-robot-prod.iam.gserviceaccount.com \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

Artifact Registry:

```bash
gcloud kms keys add-iam-policy-binding adr-agent-key \
  --location=us-central1 --keyring=adr-agent-ring \
  --member=serviceAccount:service-222222222222@gcp-sa-artifactregistry.iam.gserviceaccount.com \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

Cloud Storage — print the agent, then grant it:

```bash
gcloud storage service-agent --project=my-service-project
```

```bash
gcloud kms keys add-iam-policy-binding adr-agent-key \
  --location=us-central1 --keyring=adr-agent-ring \
  --member=serviceAccount:service-222222222222@gs-project-accounts.iam.gserviceaccount.com \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

Secret Manager:

```bash
gcloud kms keys add-iam-policy-binding adr-agent-key \
  --location=us-central1 --keyring=adr-agent-ring \
  --member=serviceAccount:service-222222222222@gcp-sa-secretmanager.iam.gserviceaccount.com \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

---

## 3. Artifact Registry (CMEK, service project)

```bash
gcloud artifacts repositories create adr-agent \
  --repository-format=docker \
  --location=us-central1 \
  --kms-key=projects/my-service-project/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key \
  --description="ADR Agent container images"
```

---

## 4. Cloud Storage (CMEK, service project) — persistent state

Cloud Run's filesystem is **ephemeral**. This bucket is mounted into the container so ADRs, KT
documents, admin config, and uploaded knowledge/skills survive restarts and scaling.

```bash
gcloud storage buckets create gs://my-service-project-adr-agent-data \
  --location=us-central1 \
  --default-encryption-key=projects/my-service-project/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key \
  --uniform-bucket-level-access \
  --public-access-prevention
```

Seed it with the built-in knowledge and skills (run from the repo root):

```bash
gcloud storage cp -r backend/app/knowledge gs://my-service-project-adr-agent-data/knowledge
```

```bash
gcloud storage cp -r backend/app/skills gs://my-service-project-adr-agent-data/skills
```

---

## 5. Secret Manager (CMEK, service project)

```bash
gcloud secrets create gemini-api-key \
  --replication-policy=user-managed \
  --locations=us-central1 \
  --kms-key-name=projects/my-service-project/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key
```

```bash
gcloud secrets create github-token \
  --replication-policy=user-managed \
  --locations=us-central1 \
  --kms-key-name=projects/my-service-project/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key
```

Add the values interactively — paste, then press **Ctrl-D**. Keeps them out of shell history:

```bash
gcloud secrets versions add gemini-api-key --data-file=-
```

```bash
gcloud secrets versions add github-token --data-file=-
```

---

## 6. Service accounts (service project — never the defaults)

```bash
gcloud iam service-accounts create adr-agent-build --display-name="ADR Agent - Cloud Build"
```

```bash
gcloud iam service-accounts create adr-agent-run --display-name="ADR Agent - Cloud Run runtime"
```

### Cloud Build SA — build and push only

```bash
gcloud projects add-iam-policy-binding my-service-project \
  --member=serviceAccount:adr-agent-build@my-service-project.iam.gserviceaccount.com \
  --role=roles/logging.logWriter
```

```bash
gcloud artifacts repositories add-iam-policy-binding adr-agent \
  --location=us-central1 \
  --member=serviceAccount:adr-agent-build@my-service-project.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer
```

```bash
gcloud storage buckets add-iam-policy-binding gs://my-service-project-adr-agent-data \
  --member=serviceAccount:adr-agent-build@my-service-project.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

> Intentionally **no** `roles/run.admin` and **no** `roles/iam.serviceAccountUser` — Cloud Build
> cannot deploy.

### Cloud Run runtime SA — least privilege

```bash
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member=serviceAccount:adr-agent-run@my-service-project.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

```bash
gcloud secrets add-iam-policy-binding github-token \
  --member=serviceAccount:adr-agent-run@my-service-project.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

```bash
gcloud storage buckets add-iam-policy-binding gs://my-service-project-adr-agent-data \
  --member=serviceAccount:adr-agent-run@my-service-project.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

```bash
gcloud projects add-iam-policy-binding my-service-project \
  --member=serviceAccount:adr-agent-run@my-service-project.iam.gserviceaccount.com \
  --role=roles/logging.logWriter
```

---

## 7. Shared VPC prerequisites (host project — verify + IAM)

### 7a. Confirm the service project is attached to the host

```bash
gcloud compute shared-vpc associated-projects list my-host-project
```

### 7b. Confirm the proxy-only subnet exists

One already exists — **do not create another** (only one ACTIVE proxy-only subnet per region
per VPC is allowed):

```bash
gcloud compute networks subnets list \
  --project=my-host-project \
  --filter="purpose=REGIONAL_MANAGED_PROXY AND region:us-central1 AND network:my-vpc" \
  --format="table(name,region,ipCidrRange,purpose,role)"
```

Expect `purpose=REGIONAL_MANAGED_PROXY` and `role=ACTIVE`. Nothing references it by name — the
internal ALB picks it up automatically for this region and VPC.

### 7c. Find the existing Zscaler egress tag

Routes and firewall rules are already in place — you are only attaching the tag. List the
routes to see which **network tag** steers traffic to Zscaler:

```bash
gcloud compute routes list \
  --project=my-host-project \
  --filter="network:my-vpc" \
  --format="table(name,destRange,priority,nextHopIlb,nextHopInstance,tags.list())"
```

Cross-check the egress firewall rules that use the same tag:

```bash
gcloud compute firewall-rules list \
  --project=my-host-project \
  --filter="network:my-vpc AND direction=EGRESS" \
  --format="table(name,direction,priority,destinationRanges.list(),targetTags.list(),allowed[].map().firewall_rule().list())"
```

➡️ **Use that exact tag** in §9 (`--network-tags=`). Replace `zscaler-egress` throughout if the
real tag differs.

> ⚠️ **Gemini traffic.** `--vpc-egress=all-traffic` (used in §9) sends Google API calls through
> the VPC too. The agent calls `generativelanguage.googleapis.com`. Confirm Zscaler allows it,
> or that Private Google Access covers it:
>
> ```bash
> gcloud compute networks subnets describe my-existing-subnet \
>   --project=my-host-project --region=us-central1 \
>   --format='value(privateIpGoogleAccess)'
> ```
>
> If this prints `False` and Zscaler does not allow that host, the agent cannot call Gemini.

### 7d. Confirm on-prem can reach the LB on 443

```bash
gcloud compute firewall-rules list \
  --project=my-host-project \
  --filter="network:my-vpc AND direction=INGRESS" \
  --format="table(name,direction,priority,sourceRanges.list(),allowed[].map().firewall_rule().list())"
```

If nothing permits `10.0.0.0/8` to `tcp:443`, ask the network team to add it (host project):

```bash
gcloud compute firewall-rules create adr-agent-allow-onprem-to-lb \
  --project=my-host-project \
  --network=my-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:443 \
  --source-ranges=10.0.0.0/8 \
  --priority=1000
```

### 7e. Grant Shared VPC access on the subnet (required)

Both the Cloud Run service agent (for Direct VPC egress) and the service project's Google APIs
agent (for creating LB resources against the shared subnet) need `compute.networkUser`.

```bash
gcloud compute networks subnets add-iam-policy-binding my-existing-subnet \
  --project=my-host-project \
  --region=us-central1 \
  --member=serviceAccount:service-222222222222@serverless-robot-prod.iam.gserviceaccount.com \
  --role=roles/compute.networkUser
```

```bash
gcloud compute networks subnets add-iam-policy-binding my-existing-subnet \
  --project=my-host-project \
  --region=us-central1 \
  --member=serviceAccount:222222222222@cloudservices.gserviceaccount.com \
  --role=roles/compute.networkUser
```

> You (the operator) also need `roles/compute.networkUser` on this subnet, plus the ability to
> create the DNS record in §11.

### 7f. DNS — nothing to do here

Name resolution is handled by the **organization's self-service DNS portal** (§11), the same
way you do it for GKE. No Cloud DNS zone, record, or inbound forwarding policy is needed.

For reference only, the pre-existing per-subnet DNS forwarder addresses can be listed with:

```bash
gcloud compute addresses list \
  --project=my-host-project \
  --filter="purpose=DNS_RESOLVER" \
  --format="table(name,region,address,subnetwork)"
```

You only need these if you ever bypass the self-service portal and resolve via Cloud DNS.

---

## 8. Build and push the image (Cloud Build — build + push only)

Run from the repository root:

```bash
gcloud builds submit \
  --region=us-central1 \
  --config=cloudbuild.yaml \
  --service-account=projects/my-service-project/serviceAccounts/adr-agent-build@my-service-project.iam.gserviceaccount.com \
  --gcs-source-staging-dir=gs://my-service-project-adr-agent-data/source \
  --substitutions=_IMAGE=us-central1-docker.pkg.dev/my-service-project/adr-agent/adr-agent:v1
```

Confirm the image landed:

```bash
gcloud artifacts docker images list us-central1-docker.pkg.dev/my-service-project/adr-agent --include-tags
```

---

## 9. Deploy Cloud Run (you run this — internal, CMEK, no public URL)

Note the **fully-qualified** network and subnet paths — required with Shared VPC.

```bash
gcloud run deploy adr-agent \
  --image=us-central1-docker.pkg.dev/my-service-project/adr-agent/adr-agent:v1 \
  --region=us-central1 \
  --service-account=adr-agent-run@my-service-project.iam.gserviceaccount.com \
  --ingress=internal-and-cloud-load-balancing \
  --no-default-url \
  --allow-unauthenticated \
  --encryption-key=projects/my-service-project/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key \
  --network=projects/my-host-project/global/networks/my-vpc \
  --subnet=projects/my-host-project/regions/us-central1/subnetworks/my-existing-subnet \
  --network-tags=zscaler-egress \
  --vpc-egress=all-traffic \
  --add-volume=name=data,type=cloud-storage,bucket=my-service-project-adr-agent-data \
  --add-volume-mount=volume=data,mount-path=/data \
  --set-secrets=GOOGLE_API_KEY=gemini-api-key:latest \
  --set-env-vars=LLM_PROVIDER=gemini,GEMINI_MODEL=gemini-flash-latest,ADR_OUTPUT_DIR=/data/adrs,DATA_DIR=/data/config,KNOWLEDGE_DIR=/data/knowledge,SKILLS_DIR=/data/skills \
  --port=8080 \
  --cpu=1 \
  --memory=1Gi \
  --min-instances=1 \
  --max-instances=4 \
  --concurrency=80 \
  --timeout=300
```

| Flag | Why |
|---|---|
| `--ingress=internal-and-cloud-load-balancing` | Unreachable from the internet; only the VPC and the internal ALB |
| `--no-default-url` | Removes the `*.run.app` URL entirely — no public hostname exists |
| `--allow-unauthenticated` | An ALB cannot mint ID tokens, so IAM auth would break browser access. **Not public** — ingress is internal; the app's own login/SSO handles identity |
| `--encryption-key` | CMEK for the service |
| `--network-tags` | Attaches to the **existing** Zscaler routes/firewall (requires Direct VPC egress) |
| `--vpc-egress=all-traffic` | All egress traverses the VPC so Zscaler policy applies |
| `--add-volume type=cloud-storage` | Persists ADRs/KT/config on the CMEK bucket |

---

## 10. Internal Application Load Balancer (service project, HTTPS only)

### 10a. Certificate (Venafi-issued)

Request the certificate for the **exact name you will register in §11** — e.g. `myapp.adr.agent`
— with that name in the **SAN** field (browsers ignore CN and match on SAN).

> ⚠️ **Internal CA required.** Public CAs cannot issue for a non-public name like
> `myapp.adr.agent` (there's no domain to validate). It must be issued by your **internal CA**,
> and your laptop must already trust that CA's root — which it will if it's the corporate root
> pushed by group policy. This is the same CA path your GKE Istio certs use.

Put the **leaf first, then intermediates** in `cert.pem` and the key in `key.pem`:

```bash
gcloud compute ssl-certificates create adr-agent-cert \
  --certificate=cert.pem \
  --private-key=key.pem \
  --region=us-central1
```

### 10b. Serverless NEG → Cloud Run

```bash
gcloud compute network-endpoint-groups create adr-agent-neg \
  --region=us-central1 \
  --network-endpoint-type=serverless \
  --cloud-run-service=adr-agent
```

### 10c. Backend service

```bash
gcloud compute backend-services create adr-agent-bes \
  --region=us-central1 \
  --load-balancing-scheme=INTERNAL_MANAGED \
  --protocol=HTTPS
```

```bash
gcloud compute backend-services add-backend adr-agent-bes \
  --region=us-central1 \
  --network-endpoint-group=adr-agent-neg \
  --network-endpoint-group-region=us-central1
```

### 10d. URL map and HTTPS proxy

```bash
gcloud compute url-maps create adr-agent-urlmap \
  --default-service=adr-agent-bes \
  --region=us-central1
```

```bash
gcloud compute target-https-proxies create adr-agent-proxy \
  --region=us-central1 \
  --url-map=adr-agent-urlmap \
  --ssl-certificates=adr-agent-cert
```

### 10e. Internal VIP and forwarding rule

The address is reserved **in the service project** but carved from the **host project's**
subnet:

```bash
gcloud compute addresses create adr-agent-vip \
  --region=us-central1 \
  --subnet=projects/my-host-project/regions/us-central1/subnetworks/my-existing-subnet
```

```bash
gcloud compute addresses describe adr-agent-vip --region=us-central1 --format='value(address)'
```

Use the printed address in §11. Create the forwarding rule (service project, host network):

```bash
gcloud compute forwarding-rules create adr-agent-fr \
  --region=us-central1 \
  --load-balancing-scheme=INTERNAL_MANAGED \
  --network=projects/my-host-project/global/networks/my-vpc \
  --subnet=projects/my-host-project/regions/us-central1/subnetworks/my-existing-subnet \
  --address=adr-agent-vip \
  --target-https-proxy=adr-agent-proxy \
  --target-https-proxy-region=us-central1 \
  --ports=443
```

> **HTTPS only.** No port-80 forwarding rule is created, so there is no HTTP listener at all.

### Do you need `--allow-global-access`?

This flag has **nothing to do with internet access** — the VIP is a private RFC1918 address
either way. It only controls whether clients in **other GCP regions** (including on-prem
traffic arriving via an Interconnect attached in a *different* region) can reach it.

```bash
gcloud compute interconnects attachments list --project=my-host-project --format="table(name,region,router)"
```

- Attachment region **is** `us-central1` → leave it off (as above).
- Attachment region **is not** `us-central1` → add it, or on-prem cannot reach the VIP:

```bash
gcloud compute forwarding-rules update adr-agent-fr --region=us-central1 --allow-global-access
```

---

## 11. DNS — register the name in the org self-service portal

**No gcloud commands here.** This mirrors the GKE flow: you reserve a static IP, then map a
custom name to it in the organization's self-service DNS portal. Cloud DNS is not used.

### 11a. Get the static VIP you reserved

```bash
gcloud compute addresses describe adr-agent-vip --region=us-central1 --format='value(address)'
```

### 11b. Submit the mapping in the self-service portal

| Field | Value |
|---|---|
| **Custom name** | `myapp.adr.agent` |
| **IP address** | the address printed above (e.g. `10.10.0.25`) |
| **Type** | A record |

Same as GKE — except there you register the Istio/LB static IP; here you register the
**internal ALB VIP**. Submit and wait for it to propagate.

### 11c. Confirm it resolves (from on-prem)

```bash
nslookup myapp.adr.agent
```

> **Naming note.** A private-only name like `myapp.adr.agent` has no public DNS delegation at
> all, so it can never resolve outside your network — this is *stronger* isolation than a
> subdomain of a real domain such as `matextechplus.com`, where a stray public record would
> expose it. If your org lets you choose the suffix, `.internal` is formally reserved by ICANN
> for private use and can never collide with a future public gTLD. Otherwise follow whatever
> namespace the self-service portal manages.

> ⚠️ **The certificate must match this exact name** — see §10a. A public CA **cannot** issue a
> certificate for a non-public name like `myapp.adr.agent`; it must come from your internal CA
> (which is what Venafi typically fronts).

---

## 12. Verify from an on-prem laptop

```bash
nslookup myapp.adr.agent
```

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://myapp.adr.agent/api/health
```

```bash
curl -sS https://myapp.adr.agent/api/health
```

Then open **https://myapp.adr.agent** in the browser and sign in.

---

## 13. Why the outside world cannot see this app

| # | Layer | Effect |
|---|---|---|
| 1 | **Non-public name** | `myapp.adr.agent` has no public DNS delegation anywhere in the world — no registrar, no zone, nothing to look up. It cannot resolve from the internet even in principle. |
| 2 | **Internal-only resolution** | The mapping lives solely in the org's self-service DNS, reachable from the corporate network. |
| 3 | **Private VIP** | `INTERNAL_MANAGED` with an RFC1918 address. No external IP is ever allocated. |
| 4 | **Cloud Run ingress** | `internal-and-cloud-load-balancing` rejects anything not from the VPC or the internal LB. |
| 5 | **No default URL** | `--no-default-url` removes the `*.run.app` hostname — the usual public backdoor doesn't exist. |
| 6 | **Firewall** | Ingress on :443 restricted to `10.0.0.0/8`. |

✅ A private-only name like `myapp.adr.agent` **eliminates** the main risk a real domain would
carry — someone accidentally publishing the record in the public zone. There is no public zone
to publish into. This is stronger isolation than `something.matextechplus.com` would give you.

Verify from **off** the corporate network:

```bash
dig +short myapp.adr.agent @8.8.8.8
```

Confirm the service has no public URL (output should be empty):

```bash
gcloud run services describe adr-agent --region=us-central1 --format='value(status.url)'
```

```bash
gcloud compute forwarding-rules describe adr-agent-fr --region=us-central1 \
  --format='value(loadBalancingScheme,IPAddress)'
```

---

## 14. Replicating in another organization

Find-and-replace the values from the table at the top, then run the same commands. Watch for:

1. **Org policies** — `run.allowedIngress` must permit internal; `gcp.restrictNonCmekServices`.
2. **Shared VPC attachment** — the service project must be attached to the host (§7a), and
   `compute.networkUser` granted on the subnet (§7e).
3. **KMS location** must match the region for every CMEK resource.
4. **Proxy-only subnet** — confirm one exists (§7b); create it only if that org lacks one.
5. **Zscaler tag** — the tag name differs per environment; re-run §7c to find it.
6. **Self-service DNS** — each org has its own portal; register the new VIP there (§11).
7. **Venafi / internal CA** — the certificate SAN must match the custom name you register in
   that org, and the laptops must trust that CA's root.

---

## 15. Updating the app later

Build a new tag:

```bash
gcloud builds submit \
  --region=us-central1 \
  --config=cloudbuild.yaml \
  --service-account=projects/my-service-project/serviceAccounts/adr-agent-build@my-service-project.iam.gserviceaccount.com \
  --gcs-source-staging-dir=gs://my-service-project-adr-agent-data/source \
  --substitutions=_IMAGE=us-central1-docker.pkg.dev/my-service-project/adr-agent/adr-agent:v2
```

Deploy it (all other settings are retained):

```bash
gcloud run services update adr-agent \
  --region=us-central1 \
  --image=us-central1-docker.pkg.dev/my-service-project/adr-agent/adr-agent:v2
```

Rotate the certificate:

```bash
gcloud compute target-https-proxies update adr-agent-proxy \
  --region=us-central1 --ssl-certificates=adr-agent-cert-new
```

---

## 16. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `PERMISSION_DENIED` mentioning KMS | A service agent is missing `cryptoKeyEncrypterDecrypter` (§2) |
| Deploy fails referencing the subnet | Missing `compute.networkUser` on the host subnet (§7e), or the subnet path isn't fully qualified |
| `Invalid value for field subnetwork` | Use `projects/my-host-project/regions/us-central1/subnetworks/my-existing-subnet`, not the bare name |
| Build fails: *"build must specify logs bucket"* | Custom build SA without `CLOUD_LOGGING_ONLY` — already set in `cloudbuild.yaml` |
| Cloud Run cannot reach GitHub | Wrong network tag — re-check §7c and match the existing route's tag exactly |
| Agent fails calling Gemini | `all-traffic` egress with no path to Google APIs — see the note in §7c |
| LB returns 502 | NEG region mismatch, or ingress not `internal-and-cloud-load-balancing` |
| On-prem cannot reach the VIP | Interconnect lands in another region — add `--allow-global-access` (§10e) |
| Name doesn't resolve on-prem | Self-service DNS mapping not submitted or not yet propagated (§11) |
| `NET::ERR_CERT_COMMON_NAME_INVALID` | Certificate SAN doesn't match the registered name — reissue for the exact custom name (§10a) |
| Cert issued by public CA rejected | A public CA cannot sign a private-only name — reissue from the internal CA (§10a) |
| ADRs disappear after a restart | Volume mount or env vars missing — `ADR_OUTPUT_DIR` must be under `/data` |
| Browser certificate warning | `cert.pem` missing intermediates, or the corporate root isn't trusted on the laptop |

---

## 17. Recommended hardening (next steps)

- **IAP** on the load balancer for an identity gate ahead of the app.
- **VPC Service Controls** perimeter around Run, Storage, Artifact Registry, KMS, Secret Manager.
- **Binary Authorization** so only Cloud Build-produced images can deploy.
- **Move the GitHub/Confluence tokens** out of the admin config file into Secret Manager (the app
  currently persists them in `app_config.json` on the CMEK bucket).
