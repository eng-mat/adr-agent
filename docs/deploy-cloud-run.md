# Deploying the ADR Agent to Cloud Run (internal, CMEK, hybrid on-prem access)

Run these commands **one after another, top to bottom**. Every command uses literal values —
no shell variables, no scripts. To reuse this in another organization, find-and-replace the
values in the table below.

**Division of labour:** Cloud Build **only builds and pushes the image** to Artifact Registry.
**You deploy Cloud Run manually** (§9). The build service account deliberately has no
`run.admin`, so the pipeline cannot touch production.

---

## Values to find-and-replace

| Placeholder in this doc | Meaning |
|---|---|
| `my-project-id` | GCP project ID |
| `123456789012` | Project **number** — `gcloud projects describe my-project-id --format='value(projectNumber)'` |
| `us-central1` | Region (must match your existing subnet + KMS) |
| `my-vpc` | Existing VPC network |
| `my-existing-subnet` | Existing app subnet (Direct VPC egress + LB VIP) |
| `zscaler-egress` | Network tag that routes egress to Zscaler |
| `10.0.0.0/8` | On-prem CIDR allowed to reach the LB |
| `myapp.beta.matextechplus.com` | Internal FQDN |

Set the project once so you don't repeat `--project` everywhere:

```bash
gcloud config set project my-project-id
gcloud config set compute/region us-central1
```

---

## Target architecture

```
 on-prem laptop
      │  DNS: myapp.beta.matextechplus.com → internal LB VIP (private)
      │  Interconnect / VPN
      ▼
 ┌──────────────────────────────────────────────┐
 │ VPC: my-vpc                                  │
 │  Internal Application LB (HTTPS :443)        │
 │   • existing proxy-only subnet               │
 │   • Venafi cert                              │
 │            │ serverless NEG                  │
 │            ▼                                 │
 │  Cloud Run (INTERNAL ingress, no public URL) │
 │   • CMEK · GCS volume (CMEK) · Secret Mgr    │
 │            │ egress tag: zscaler-egress      │
 │            ▼ route → Zscaler → GitHub        │
 └──────────────────────────────────────────────┘
```

---

## 1. Enable APIs

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

Check for org policies that commonly block this build (do this first in a new org):

```bash
gcloud resource-manager org-policies list --project=my-project-id
```

Watch for: `constraints/run.allowedIngress`, `constraints/gcp.restrictNonCmekServices`,
`constraints/compute.restrictSharedVpcSubnetworks`, domain-restricted sharing.

---

## 2. KMS — one CMEK key for everything

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

CMEK is applied by **service agents**, not by your own service accounts. A missing grant here
is the single most common cause of deploy failures.

Create the service identities first (no-ops if they already exist):

```bash
gcloud beta services identity create --service=artifactregistry.googleapis.com --project=my-project-id
gcloud beta services identity create --service=secretmanager.googleapis.com --project=my-project-id
```

Cloud Run:

```bash
gcloud kms keys add-iam-policy-binding adr-agent-key \
  --location=us-central1 --keyring=adr-agent-ring \
  --member=serviceAccount:service-123456789012@serverless-robot-prod.iam.gserviceaccount.com \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

Artifact Registry:

```bash
gcloud kms keys add-iam-policy-binding adr-agent-key \
  --location=us-central1 --keyring=adr-agent-ring \
  --member=serviceAccount:service-123456789012@gcp-sa-artifactregistry.iam.gserviceaccount.com \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

Cloud Storage (print the agent first, then grant it):

```bash
gcloud storage service-agent --project=my-project-id
```

```bash
gcloud kms keys add-iam-policy-binding adr-agent-key \
  --location=us-central1 --keyring=adr-agent-ring \
  --member=serviceAccount:service-123456789012@gs-project-accounts.iam.gserviceaccount.com \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

Secret Manager:

```bash
gcloud kms keys add-iam-policy-binding adr-agent-key \
  --location=us-central1 --keyring=adr-agent-ring \
  --member=serviceAccount:service-123456789012@gcp-sa-secretmanager.iam.gserviceaccount.com \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

---

## 3. Artifact Registry (CMEK)

```bash
gcloud artifacts repositories create adr-agent \
  --repository-format=docker \
  --location=us-central1 \
  --kms-key=projects/my-project-id/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key \
  --description="ADR Agent container images"
```

---

## 4. Cloud Storage (CMEK) — persistent state

Cloud Run's filesystem is **ephemeral**. This bucket is mounted into the container so ADRs,
KT documents, admin config, and uploaded knowledge/skills survive restarts and scaling.

```bash
gcloud storage buckets create gs://my-project-id-adr-agent-data \
  --location=us-central1 \
  --default-encryption-key=projects/my-project-id/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key \
  --uniform-bucket-level-access \
  --public-access-prevention
```

Seed the bucket with the built-in knowledge and skills so admin uploads land beside them
(run from the repo root):

```bash
gcloud storage cp -r backend/app/knowledge gs://my-project-id-adr-agent-data/knowledge
```

```bash
gcloud storage cp -r backend/app/skills gs://my-project-id-adr-agent-data/skills
```

---

## 5. Secret Manager (CMEK)

```bash
gcloud secrets create gemini-api-key \
  --replication-policy=user-managed \
  --locations=us-central1 \
  --kms-key-name=projects/my-project-id/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key
```

```bash
gcloud secrets create github-token \
  --replication-policy=user-managed \
  --locations=us-central1 \
  --kms-key-name=projects/my-project-id/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key
```

Add the values interactively — paste the secret, then press **Ctrl-D**. This keeps them out of
shell history:

```bash
gcloud secrets versions add gemini-api-key --data-file=-
```

```bash
gcloud secrets versions add github-token --data-file=-
```

---

## 6. Service accounts (never the default SAs)

```bash
gcloud iam service-accounts create adr-agent-build --display-name="ADR Agent - Cloud Build"
```

```bash
gcloud iam service-accounts create adr-agent-run --display-name="ADR Agent - Cloud Run runtime"
```

### Cloud Build SA — build and push only

Write build logs (required when using a custom build SA):

```bash
gcloud projects add-iam-policy-binding my-project-id \
  --member=serviceAccount:adr-agent-build@my-project-id.iam.gserviceaccount.com \
  --role=roles/logging.logWriter
```

Push images — scoped to this repository only:

```bash
gcloud artifacts repositories add-iam-policy-binding adr-agent \
  --location=us-central1 \
  --member=serviceAccount:adr-agent-build@my-project-id.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer
```

Upload build source — scoped to this bucket only:

```bash
gcloud storage buckets add-iam-policy-binding gs://my-project-id-adr-agent-data \
  --member=serviceAccount:adr-agent-build@my-project-id.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

> Intentionally **no** `roles/run.admin` and **no** `roles/iam.serviceAccountUser`. Cloud Build
> cannot deploy — you do that yourself in §9.

### Cloud Run runtime SA — least privilege

Read the two secrets (scoped per-secret, not project-wide):

```bash
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member=serviceAccount:adr-agent-run@my-project-id.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

```bash
gcloud secrets add-iam-policy-binding github-token \
  --member=serviceAccount:adr-agent-run@my-project-id.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

Read/write the mounted bucket:

```bash
gcloud storage buckets add-iam-policy-binding gs://my-project-id-adr-agent-data \
  --member=serviceAccount:adr-agent-run@my-project-id.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

Application logs:

```bash
gcloud projects add-iam-policy-binding my-project-id \
  --member=serviceAccount:adr-agent-run@my-project-id.iam.gserviceaccount.com \
  --role=roles/logging.logWriter
```

---

## 7. Networking

### 7a. Confirm the existing proxy-only subnet

One already exists in this network — **do not create another** (only one ACTIVE proxy-only
subnet per region per VPC is allowed). Just confirm it is in the right region and `ACTIVE`:

```bash
gcloud compute networks subnets list \
  --filter="purpose=REGIONAL_MANAGED_PROXY AND region:us-central1 AND network:my-vpc" \
  --format="table(name,region,ipCidrRange,purpose,role)"
```

Expect `purpose=REGIONAL_MANAGED_PROXY` and `role=ACTIVE`. Nothing references it by name — the
internal ALB picks it up automatically for this region/VPC.

### 7b. Egress to Zscaler via the network tag

Cloud Run **Direct VPC egress** supports network tags, so your existing tag-based routing and
firewall rules apply exactly as they do for VMs.

Route tagged egress to Zscaler (adjust the next hop to your environment):

```bash
gcloud compute routes create adr-agent-zscaler-egress \
  --network=my-vpc \
  --destination-range=0.0.0.0/0 \
  --tags=zscaler-egress \
  --priority=100 \
  --next-hop-ilb=zscaler-ilb --next-hop-ilb-region=us-central1
```

Allow the tagged egress:

```bash
gcloud compute firewall-rules create adr-agent-allow-egress-zscaler \
  --network=my-vpc \
  --direction=EGRESS \
  --action=ALLOW \
  --rules=tcp:443 \
  --destination-ranges=0.0.0.0/0 \
  --target-tags=zscaler-egress \
  --priority=1000
```

> ⚠️ **`--vpc-egress=all-traffic` (used in §9) sends Google API traffic through the VPC too.**
> The agent calls `generativelanguage.googleapis.com` (Gemini). Either allowlist that in
> Zscaler, **or** keep Google APIs on-net with Private Google Access:
>
> ```bash
> gcloud compute networks subnets update my-existing-subnet \
>   --region=us-central1 --enable-private-ip-google-access
> ```
>
> ```bash
> gcloud compute routes create adr-agent-private-googleapis \
>   --network=my-vpc \
>   --destination-range=199.36.153.8/30 \
>   --next-hop-gateway=default-internet-gateway \
>   --tags=zscaler-egress \
>   --priority=90
> ```
>
> Use `199.36.153.4/30` with `restricted.googleapis.com` if you are inside a VPC-SC perimeter.

### 7c. Allow on-prem clients to reach the LB

```bash
gcloud compute firewall-rules create adr-agent-allow-onprem-to-lb \
  --network=my-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:443 \
  --source-ranges=10.0.0.0/8 \
  --priority=1000
```

---

## 8. Build and push the image (Cloud Build — build + push only)

Run from the repository root. Cloud Build uses your custom service account and pushes to
Artifact Registry. It does **not** deploy.

```bash
gcloud builds submit \
  --region=us-central1 \
  --config=cloudbuild.yaml \
  --service-account=projects/my-project-id/serviceAccounts/adr-agent-build@my-project-id.iam.gserviceaccount.com \
  --gcs-source-staging-dir=gs://my-project-id-adr-agent-data/source \
  --substitutions=_IMAGE=us-central1-docker.pkg.dev/my-project-id/adr-agent/adr-agent:v1
```

Confirm the image landed:

```bash
gcloud artifacts docker images list us-central1-docker.pkg.dev/my-project-id/adr-agent \
  --include-tags
```

---

## 9. Deploy Cloud Run (you run this — internal, CMEK, no public URL)

```bash
gcloud run deploy adr-agent \
  --image=us-central1-docker.pkg.dev/my-project-id/adr-agent/adr-agent:v1 \
  --region=us-central1 \
  --service-account=adr-agent-run@my-project-id.iam.gserviceaccount.com \
  --ingress=internal-and-cloud-load-balancing \
  --no-default-url \
  --allow-unauthenticated \
  --encryption-key=projects/my-project-id/locations/us-central1/keyRings/adr-agent-ring/cryptoKeys/adr-agent-key \
  --network=my-vpc \
  --subnet=my-existing-subnet \
  --network-tags=zscaler-egress \
  --vpc-egress=all-traffic \
  --add-volume=name=data,type=cloud-storage,bucket=my-project-id-adr-agent-data \
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

What the key flags do:

| Flag | Why |
|---|---|
| `--ingress=internal-and-cloud-load-balancing` | Unreachable from the internet; only your VPC and the internal ALB |
| `--no-default-url` | Removes the `*.run.app` URL entirely — no public hostname exists |
| `--allow-unauthenticated` | An ALB cannot mint ID tokens, so IAM auth would break browser access. **Not public** — ingress is internal; the app's own login/SSO handles identity |
| `--encryption-key` | CMEK for the service |
| `--network-tags` | Requires Direct VPC egress; drives the Zscaler route and firewall |
| `--vpc-egress=all-traffic` | All egress traverses the VPC so Zscaler policy applies |
| `--add-volume type=cloud-storage` | Persists ADRs/KT/config on the CMEK bucket |

---

## 10. Internal Application Load Balancer (HTTPS only)

### 10a. Certificate (Venafi-issued)

Obtain the certificate for `myapp.beta.matextechplus.com` from Venafi. Put the **leaf first,
then intermediates** in `cert.pem`, and the key in `key.pem`, then upload as a **regional**
self-managed certificate:

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

```bash
gcloud compute addresses create adr-agent-vip \
  --region=us-central1 \
  --subnet=my-existing-subnet
```

```bash
gcloud compute addresses describe adr-agent-vip \
  --region=us-central1 --format='value(address)'
```

Use the address printed above in the next command (and again in §11):

```bash
gcloud compute forwarding-rules create adr-agent-fr \
  --region=us-central1 \
  --load-balancing-scheme=INTERNAL_MANAGED \
  --network=my-vpc \
  --subnet=my-existing-subnet \
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

On-prem clients are treated as being in the region of their VLAN attachment:

```bash
gcloud compute interconnects attachments list --format="table(name,region,router)"
```

- Attachment region **is** `us-central1` → leave it off (as above).
- Attachment region **is not** `us-central1` → add it, or on-prem cannot reach the VIP:

```bash
gcloud compute forwarding-rules update adr-agent-fr \
  --region=us-central1 --allow-global-access
```

---

## 11. DNS — myapp.beta.matextechplus.com

Private zone visible only to the VPC:

```bash
gcloud dns managed-zones create matextechplus-private \
  --dns-name=matextechplus.com. \
  --visibility=private \
  --networks=my-vpc \
  --description="Internal zone for ADR Agent"
```

A record pointing at the LB VIP (substitute the address printed in §10e):

```bash
gcloud dns record-sets create myapp.beta.matextechplus.com. \
  --zone=matextechplus-private \
  --type=A \
  --ttl=300 \
  --rrdatas=10.10.0.25
```

### Let on-prem resolve it

```bash
gcloud dns policies create adr-agent-inbound \
  --networks=my-vpc \
  --enable-inbound-forwarding \
  --description="On-prem to Cloud DNS"
```

Get the forwarder IPs to give your corporate DNS team for a conditional forwarder on
`matextechplus.com`:

```bash
gcloud compute addresses list --filter="purpose=DNS_RESOLVER AND region:us-central1"
```

*(Alternative: skip inbound forwarding and just add an A record for `myapp.beta` on your
on-prem DNS pointing at the same VIP.)*

---

## 12. Verify from an on-prem laptop

```bash
nslookup myapp.beta.matextechplus.com
```

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://myapp.beta.matextechplus.com/api/health
```

```bash
curl -sS https://myapp.beta.matextechplus.com/api/health
```

Then open **https://myapp.beta.matextechplus.com** in the browser and sign in.

---

## 13. Why the outside world cannot see this app

Five independent layers — any one alone would block public access:

| # | Layer | Effect |
|---|---|---|
| 1 | **No public DNS record** | The name exists only in a Cloud DNS **private** zone. Public resolvers return NXDOMAIN — an outsider clicking the link resolves nothing. |
| 2 | **Private VIP** | `INTERNAL_MANAGED` with an RFC1918 address. No external IP is ever allocated. |
| 3 | **Cloud Run ingress** | `internal-and-cloud-load-balancing` rejects anything not from the VPC or the internal LB. |
| 4 | **No default URL** | `--no-default-url` removes the `*.run.app` hostname, so the usual public backdoor doesn't exist. |
| 5 | **Firewall** | Ingress on :443 restricted to `10.0.0.0/8`. |

⚠️ **The one thing that would break this:** `matextechplus.com` is a real public domain. If a
`myapp.beta` record is ever added to the **public** zone or registrar, layer 1 collapses. Keep
the record in the private zone only.

Verify from **off** your corporate network:

```bash
dig +short myapp.beta.matextechplus.com @8.8.8.8
```

Confirm the service has no public URL (output should be empty):

```bash
gcloud run services describe adr-agent --region=us-central1 --format='value(status.url)'
```

```bash
gcloud compute forwarding-rules describe adr-agent-fr \
  --region=us-central1 --format='value(loadBalancingScheme,IPAddress)'
```

---

## 14. Replicating in another organization

Find-and-replace the values from the table at the top, then run the same commands. Watch for:

1. **Org policies** — `run.allowedIngress` must permit internal; `gcp.restrictNonCmekServices`.
2. **Shared VPC** — if the subnet lives in a host project, run §7 there and grant
   `roles/compute.networkUser` on the subnet to `adr-agent-run@...` and the Cloud Run service agent.
3. **KMS location** must match the region for every CMEK resource.
4. **Proxy-only subnet** — confirm one exists (§7a); create it only if the other org lacks one.
5. **Zscaler next hop** differs per environment — only the route in §7b changes.
6. **Venafi** — certificate issuance and renewal process.

---

## 15. Updating the app later

Build a new tag:

```bash
gcloud builds submit \
  --region=us-central1 \
  --config=cloudbuild.yaml \
  --service-account=projects/my-project-id/serviceAccounts/adr-agent-build@my-project-id.iam.gserviceaccount.com \
  --gcs-source-staging-dir=gs://my-project-id-adr-agent-data/source \
  --substitutions=_IMAGE=us-central1-docker.pkg.dev/my-project-id/adr-agent/adr-agent:v2
```

Deploy it (all other settings are retained):

```bash
gcloud run services update adr-agent \
  --region=us-central1 \
  --image=us-central1-docker.pkg.dev/my-project-id/adr-agent/adr-agent:v2
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
| Build fails: *"build must specify logs bucket"* | Custom build SA without `CLOUD_LOGGING_ONLY` — already set in `cloudbuild.yaml` |
| Cloud Run cannot reach GitHub | Route/firewall for tag `zscaler-egress` (§7b), or Zscaler policy |
| Agent fails calling Gemini | `all-traffic` egress with no path to Google APIs — see the Private Google Access note in §7b |
| LB returns 502 | NEG region mismatch, or ingress not `internal-and-cloud-load-balancing` |
| On-prem cannot reach the VIP | Interconnect lands in another region — add `--allow-global-access` (§10e) |
| ADRs disappear after a restart | Volume mount or env vars missing — `ADR_OUTPUT_DIR` must be under `/data` |
| Browser certificate warning | `cert.pem` missing intermediates, or the corporate root is not trusted on the laptop |

---

## 17. Recommended hardening (next steps)

- **IAP** on the load balancer for an identity gate ahead of the app.
- **VPC Service Controls** perimeter around Run, Storage, Artifact Registry, KMS, Secret Manager.
- **Binary Authorization** so only Cloud Build-produced images can deploy.
- **Move the GitHub/Confluence tokens** out of the admin config file into Secret Manager (the app
  currently persists them in `app_config.json` on the CMEK bucket).
