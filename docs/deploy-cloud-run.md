# Deploying the ADR Agent to Cloud Run (internal, CMEK, hybrid on-prem access)

A parameterized runbook. Set the variables in **§1**, then run each section in order.
Everything is written to be re-runnable in a second organization by changing only §1.

## Target architecture

```
 on-prem laptop
      │  (DNS: myapp.beta.matextechplus.com  →  internal LB VIP)
      │  Interconnect / VPN
      ▼
 ┌──────────────────────────────────────────────┐
 │ VPC (existing subnet)                        │
 │                                              │
 │  Internal Application LB (HTTPS :443)        │
 │   • regional, proxy-only subnet              │
 │   • Venafi-issued cert                       │
 │   • --allow-global-access (on-prem reach)    │
 │            │ serverless NEG                  │
 │            ▼                                 │
 │  Cloud Run service (INTERNAL ingress only)   │
 │   • CMEK encrypted, no default run.app URL   │
 │   • Direct VPC egress + network tag          │
 │   • GCS volume mount (CMEK) for persistence  │
 │   • Secrets from Secret Manager (CMEK)       │
 │            │ egress (tag: zscaler-egress)    │
 │            ▼ route → Zscaler → GitHub        │
 └──────────────────────────────────────────────┘
```

**Why `--allow-unauthenticated` is still safe here:** with `--ingress=internal-and-cloud-load-balancing`
the service is unreachable from the internet — the network is the boundary. Cloud Run IAM auth
can't be used for browser traffic behind an ALB (the LB doesn't mint ID tokens), so user identity
is handled by the app's own login/SSO. If you later want an identity gate at the edge, add IAP.

---

## 1. Variables

```bash
# ---- identity / location ----
export PROJECT_ID="my-project"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export REGION="us-central1"

# ---- existing network (already in place) ----
export VPC="my-vpc"
export SUBNET="my-existing-subnet"            # app subnet (Direct VPC egress + LB VIP)
export PROXY_SUBNET="proxy-only-$REGION"      # NEW, required by the internal ALB
export PROXY_CIDR="10.30.0.0/24"              # must not overlap anything
export NET_TAG="zscaler-egress"               # network tag driving egress to Zscaler
export ONPREM_CIDR="10.0.0.0/8"               # on-prem ranges allowed to reach the LB

# ---- naming ----
export APP="adr-agent"
export SERVICE="$APP"
export AR_REPO="$APP"
export BUCKET="$PROJECT_ID-$APP-data"
export KMS_RING="$APP-ring"
export KMS_KEY="$APP-key"
export BUILD_SA="$APP-build@$PROJECT_ID.iam.gserviceaccount.com"
export RUN_SA="$APP-run@$PROJECT_ID.iam.gserviceaccount.com"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO/$APP:v1"

# ---- DNS ----
export DNS_ZONE="matextechplus-private"
export DNS_NAME="matextechplus.com."
export FQDN="myapp.beta.matextechplus.com"

gcloud config set project "$PROJECT_ID"
```

---

## 2. Enable APIs

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

> **Org-policy check (do this first in a new org).** These commonly block the build:
> `constraints/run.allowedIngress`, `constraints/gcp.restrictNonCmekServices`,
> `constraints/iam.disableServiceAccountKeyCreation`, `constraints/compute.vmExternalIpAccess`,
> `constraints/cloudbuild.allowedIntegrations`. Verify with:
> `gcloud resource-manager org-policies list --project=$PROJECT_ID`

---

## 3. KMS — one CMEK key for everything

The key must live in the **same region** as the resources it protects.

```bash
gcloud kms keyrings create "$KMS_RING" --location="$REGION"

gcloud kms keys create "$KMS_KEY" \
  --location="$REGION" --keyring="$KMS_RING" \
  --purpose=encryption \
  --rotation-period=90d --next-rotation-time="$(date -u -d '+90 days' +%Y-%m-%dT%H:%M:%SZ)"

export KEY="projects/$PROJECT_ID/locations/$REGION/keyRings/$KMS_RING/cryptoKeys/$KMS_KEY"
```

### Grant each Google service agent use of the key
CMEK is applied by **service agents**, not your SA. Missing any of these is the #1 failure.

```bash
# Cloud Run
gcloud kms keys add-iam-policy-binding "$KMS_KEY" \
  --location="$REGION" --keyring="$KMS_RING" \
  --member="serviceAccount:service-$PROJECT_NUMBER@serverless-robot-prod.iam.gserviceaccount.com" \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter

# Artifact Registry
gcloud beta services identity create --service=artifactregistry.googleapis.com --project="$PROJECT_ID"
gcloud kms keys add-iam-policy-binding "$KMS_KEY" \
  --location="$REGION" --keyring="$KMS_RING" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-artifactregistry.iam.gserviceaccount.com" \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter

# Cloud Storage
export GCS_AGENT="$(gcloud storage service-agent --project=$PROJECT_ID)"
gcloud kms keys add-iam-policy-binding "$KMS_KEY" \
  --location="$REGION" --keyring="$KMS_RING" \
  --member="serviceAccount:$GCS_AGENT" \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter

# Secret Manager
gcloud beta services identity create --service=secretmanager.googleapis.com --project="$PROJECT_ID"
gcloud kms keys add-iam-policy-binding "$KMS_KEY" \
  --location="$REGION" --keyring="$KMS_RING" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-secretmanager.iam.gserviceaccount.com" \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

---

## 4. Artifact Registry (CMEK)

```bash
gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --kms-key="$KEY" \
  --description="ADR Agent container images"
```

---

## 5. Cloud Storage (CMEK) — persistent state

Cloud Run's filesystem is **ephemeral**. This bucket is mounted into the container so ADRs,
KT documents, admin config, uploaded knowledge, and skills survive restarts.

```bash
gcloud storage buckets create "gs://$BUCKET" \
  --location="$REGION" \
  --default-encryption-key="$KEY" \
  --uniform-bucket-level-access \
  --public-access-prevention

# Seed the bucket with the built-in knowledge & skills so admin uploads persist alongside them
gcloud storage cp -r backend/app/knowledge "gs://$BUCKET/knowledge"
gcloud storage cp -r backend/app/skills    "gs://$BUCKET/skills"
```

---

## 6. Secret Manager (CMEK)

Never bake the Gemini key or GitHub token into the image or env vars.

```bash
for S in gemini-api-key github-token; do
  gcloud secrets create "$S" \
    --replication-policy=user-managed \
    --locations="$REGION" \
    --kms-key-name="$KEY"
done
```

Add the values **yourself** (keeps them out of shell history and CI logs):

```bash
# paste value, then press Ctrl-D
gcloud secrets versions add gemini-api-key --data-file=-
gcloud secrets versions add github-token   --data-file=-
```

---

## 7. Service accounts (no default SAs)

```bash
gcloud iam service-accounts create "$APP-build" --display-name="ADR Agent – Cloud Build"
gcloud iam service-accounts create "$APP-run"   --display-name="ADR Agent – Cloud Run runtime"
```

### Cloud Build SA — least privilege (build + push only)

```bash
# write build logs (required when using a custom SA)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$BUILD_SA" --role=roles/logging.logWriter

# push images — scoped to this repo only
gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" \
  --location="$REGION" --member="serviceAccount:$BUILD_SA" --role=roles/artifactregistry.writer

# upload build source — scoped to this bucket only
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$BUILD_SA" --role=roles/storage.objectAdmin
```

> If you later want Cloud Build to **deploy** as well, add `roles/run.admin` plus
> `roles/iam.serviceAccountUser` on `$RUN_SA`. Kept off here so the build SA can't reach production.

### Cloud Run runtime SA — least privilege

```bash
# read the two secrets (scoped per-secret, not project-wide)
for S in gemini-api-key github-token; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:$RUN_SA" --role=roles/secretmanager.secretAccessor
done

# read/write the mounted bucket
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$RUN_SA" --role=roles/storage.objectAdmin

# application logs
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUN_SA" --role=roles/logging.logWriter
```

---

## 8. Networking

### 8a. Proxy-only subnet (required by the internal ALB)

```bash
gcloud compute networks subnets create "$PROXY_SUBNET" \
  --purpose=REGIONAL_MANAGED_PROXY \
  --role=ACTIVE \
  --region="$REGION" \
  --network="$VPC" \
  --range="$PROXY_CIDR"
```

### 8b. Egress to Zscaler via the network tag

Cloud Run **Direct VPC egress** supports network tags, so the same tag-based routing/firewall
you use for VMs applies. Point the next hop at your existing Zscaler path.

```bash
# Route tagged egress to Zscaler (adjust next-hop to your environment)
gcloud compute routes create "$APP-zscaler-egress" \
  --network="$VPC" \
  --destination-range=0.0.0.0/0 \
  --tags="$NET_TAG" \
  --priority=100 \
  --next-hop-ilb=ZSCALER_ILB_NAME --next-hop-ilb-region="$REGION"
  # or: --next-hop-instance=ZSCALER_CONNECTOR --next-hop-instance-zone=ZONE

# Allow the tagged egress
gcloud compute firewall-rules create "$APP-allow-egress-zscaler" \
  --network="$VPC" --direction=EGRESS --action=ALLOW \
  --rules=tcp:443 --destination-ranges=0.0.0.0/0 --target-tags="$NET_TAG" --priority=1000
```

> ⚠️ **`--vpc-egress=all-traffic` sends Google API traffic through the VPC too.** The agent calls
> `generativelanguage.googleapis.com` (Gemini). Either allowlist it in Zscaler, **or** keep Google
> APIs on-net with Private Google Access:
> ```bash
> gcloud compute networks subnets update "$SUBNET" --region="$REGION" \
>   --enable-private-ip-google-access
> gcloud compute routes create "$APP-private-googleapis" \
>   --network="$VPC" --destination-range=199.36.153.8/30 \
>   --next-hop-gateway=default-internet-gateway --tags="$NET_TAG" --priority=90
> ```
> (use `199.36.153.4/30` + `restricted.googleapis.com` if you're inside a VPC-SC perimeter)

### 8c. Allow on-prem clients to the LB

```bash
gcloud compute firewall-rules create "$APP-allow-onprem-to-lb" \
  --network="$VPC" --direction=INGRESS --action=ALLOW \
  --rules=tcp:443 --source-ranges="$ONPREM_CIDR" --priority=1000
```

---

## 9. Build & push the image (custom SA, never the default)

```bash
gcloud builds submit \
  --region="$REGION" \
  --config=cloudbuild.yaml \
  --service-account="projects/$PROJECT_ID/serviceAccounts/$BUILD_SA" \
  --gcs-source-staging-dir="gs://$BUCKET/source" \
  --substitutions="_IMAGE=$IMAGE"
```

---

## 10. Deploy Cloud Run — internal, CMEK, no public URL

```bash
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUN_SA" \
  \
  `# --- no public exposure ---` \
  --ingress=internal-and-cloud-load-balancing \
  --no-default-url \
  --allow-unauthenticated \
  \
  `# --- CMEK ---` \
  --encryption-key="$KEY" \
  \
  `# --- Direct VPC egress + network tag (Zscaler) ---` \
  --network="$VPC" \
  --subnet="$SUBNET" \
  --network-tags="$NET_TAG" \
  --vpc-egress=all-traffic \
  \
  `# --- persistent state on the CMEK bucket ---` \
  --add-volume="name=data,type=cloud-storage,bucket=$BUCKET" \
  --add-volume-mount="volume=data,mount-path=/data" \
  \
  `# --- secrets ---` \
  --set-secrets="GOOGLE_API_KEY=gemini-api-key:latest" \
  \
  `# --- app config ---` \
  --set-env-vars="LLM_PROVIDER=gemini,GEMINI_MODEL=gemini-flash-latest,ADR_OUTPUT_DIR=/data/adrs,DATA_DIR=/data/config,KNOWLEDGE_DIR=/data/knowledge,SKILLS_DIR=/data/skills" \
  \
  --port=8080 --cpu=1 --memory=1Gi \
  --min-instances=1 --max-instances=4 --concurrency=80 --timeout=300
```

Key flags:
| Flag | Why |
|---|---|
| `--ingress=internal-and-cloud-load-balancing` | Not reachable from the internet; only VPC + the internal ALB |
| `--no-default-url` | Removes the `*.run.app` URL entirely — no protocol exposed outside the LB |
| `--encryption-key` | CMEK for the service |
| `--network-tags` | Requires Direct VPC egress; drives the Zscaler route/firewall |
| `--vpc-egress=all-traffic` | All egress traverses the VPC so Zscaler policy applies |
| `--add-volume type=cloud-storage` | Persists ADRs/KT/config on the CMEK bucket |

---

## 11. Internal Application Load Balancer (HTTPS)

### 11a. Certificate (Venafi-issued)

Obtain the cert for `$FQDN` from Venafi, then upload as a **regional** self-managed cert.
Include the full chain in `cert.pem` (leaf first, then intermediates).

```bash
gcloud compute ssl-certificates create "$APP-cert" \
  --certificate=cert.pem \
  --private-key=key.pem \
  --region="$REGION"
```

<details><summary>Alternative: Certificate Manager + Private CA</summary>

```bash
gcloud privateca pools create "$APP-pool" --location="$REGION" --tier=DEVOPS
gcloud certificate-manager certificates create "$APP-cert" \
  --domains="$FQDN" --issuance-config=... --location="$REGION"
```
</details>

### 11b. LB components

```bash
# serverless NEG → Cloud Run
gcloud compute network-endpoint-groups create "$APP-neg" \
  --region="$REGION" --network-endpoint-type=serverless --cloud-run-service="$SERVICE"

# backend service (internal managed)
gcloud compute backend-services create "$APP-bes" \
  --region="$REGION" --load-balancing-scheme=INTERNAL_MANAGED --protocol=HTTPS

gcloud compute backend-services add-backend "$APP-bes" \
  --region="$REGION" \
  --network-endpoint-group="$APP-neg" --network-endpoint-group-region="$REGION"

# url map + https proxy
gcloud compute url-maps create "$APP-urlmap" --default-service="$APP-bes" --region="$REGION"
gcloud compute target-https-proxies create "$APP-proxy" \
  --region="$REGION" --url-map="$APP-urlmap" --ssl-certificates="$APP-cert"

# static internal VIP in the existing subnet
gcloud compute addresses create "$APP-vip" --region="$REGION" --subnet="$SUBNET"
export LB_IP="$(gcloud compute addresses describe "$APP-vip" --region="$REGION" --format='value(address)')"

# forwarding rule — global access lets on-prem/other regions reach it
gcloud compute forwarding-rules create "$APP-fr" \
  --region="$REGION" --load-balancing-scheme=INTERNAL_MANAGED \
  --network="$VPC" --subnet="$SUBNET" --address="$LB_IP" \
  --target-https-proxy="$APP-proxy" --target-https-proxy-region="$REGION" \
  --ports=443 --allow-global-access

echo "LB VIP: $LB_IP"
```

> **HTTPS only.** No HTTP forwarding rule is created, so there is no port-80 listener at all.

---

## 12. DNS — `myapp.beta.matextechplus.com`

```bash
# private zone visible to the VPC
gcloud dns managed-zones create "$DNS_ZONE" \
  --dns-name="$DNS_NAME" --visibility=private --networks="$VPC" \
  --description="Internal zone for $APP"

# A record → internal LB VIP
gcloud dns record-sets create "$FQDN." \
  --zone="$DNS_ZONE" --type=A --ttl=300 --rrdatas="$LB_IP"
```

### Let on-prem resolve it
Create an **inbound** DNS forwarding entry point, then point your corporate DNS at it with a
conditional forwarder for `matextechplus.com`.

```bash
gcloud dns policies create "$APP-inbound" \
  --networks="$VPC" --enable-inbound-forwarding --description="On-prem → Cloud DNS"

# the IPs your on-prem resolver should forward to:
gcloud compute addresses list --filter="purpose=DNS_RESOLVER AND region:$REGION"
```

*(Alternative: just add an A record for `myapp.beta` on your on-prem DNS pointing at `$LB_IP`.)*

---

## 13. Verify from an on-prem laptop

```bash
nslookup myapp.beta.matextechplus.com          # → LB VIP
curl -sS -o /dev/null -w '%{http_code}\n' https://myapp.beta.matextechplus.com/api/health
curl -sS https://myapp.beta.matextechplus.com/api/health | jq
```

Then open **https://myapp.beta.matextechplus.com** in the browser and sign in.

Confirm there is **no** public exposure:
```bash
gcloud run services describe "$SERVICE" --region="$REGION" \
  --format='value(status.url, spec.template.metadata.annotations)'   # url should be empty
```

---

## 14. Replicating in another organization

Change only §1, then re-run. Watch for:

1. **Org policies** — `run.allowedIngress` (must permit internal), `gcp.restrictNonCmekServices`,
   `compute.restrictSharedVpcSubnetworks`, domain-restricted sharing.
2. **Shared VPC** — if the subnet lives in a host project, run network steps there and grant
   `roles/compute.networkUser` on the subnet to `$RUN_SA` and the Cloud Run service agent.
3. **KMS location** must match `$REGION` for every CMEK resource.
4. **Proxy-only subnet is one-per-region-per-VPC** — if another LB already created it, reuse it.
5. **Zscaler next hop** differs per environment — only the route in §8b changes.
6. **Venafi** — cert issuance/renewal process; rotate with
   `gcloud compute target-https-proxies update ... --ssl-certificates=NEW_CERT`.

---

## 15. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `PERMISSION_DENIED` on deploy referencing KMS | A service agent is missing `cryptoKeyEncrypterDecrypter` (§3) |
| Build fails: *"build must specify logs bucket"* | Custom SA without `CLOUD_LOGGING_ONLY` — it's set in `cloudbuild.yaml` |
| Cloud Run can't reach GitHub | Route/firewall for `$NET_TAG` (§8b), or Zscaler policy |
| Agent fails calling Gemini | `all-traffic` egress with no path to Google APIs — see the Private Google Access note in §8b |
| LB returns 502 | Serverless NEG region mismatch, or ingress not `internal-and-cloud-load-balancing` |
| On-prem can't reach the VIP | Missing `--allow-global-access` on the forwarding rule, or no route advertised over Interconnect |
| ADRs disappear after a restart | Volume mount/env vars missing — `ADR_OUTPUT_DIR` must point under `/data` |
| Cert errors in browser | `cert.pem` missing intermediates; corporate root must be trusted on the laptop |

---

## 16. Recommended hardening (next steps)

- **IAP** on the LB for an identity gate ahead of the app.
- **VPC Service Controls** perimeter around Run/Storage/Artifact Registry/KMS/Secret Manager.
- **Binary Authorization** so only Cloud Build-signed images deploy.
- **Move GitHub/Confluence tokens** out of the admin config file into Secret Manager
  (the app currently persists them in `app_config.json` on the CMEK bucket).
- **Cloud Armor** is not applicable to internal ALBs; rely on firewall + on-prem controls.
