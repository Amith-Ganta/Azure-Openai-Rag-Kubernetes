# Azure OpenAI RAG on Kubernetes

A Retrieval-Augmented Generation (RAG) API for investor-intelligence Q&A over
company financial filings, containerized and deployed to **Azure Kubernetes
Service (AKS)** with a fully automated **GitHub Actions** pipeline.

The application (FastAPI + Azure OpenAI + Azure AI Search) is the coursework
foundation from Krish Naik's Agentic-AI course. This repository adds the
production deployment layer that the course left as an exercise: the
infrastructure-as-code to provision the cluster, the corrected Kubernetes
manifests, and a CI/CD pipeline that authenticates to Azure with **Entra ID
workload-identity federation (OIDC)** — no long-lived secrets stored in GitHub.

---

## Architecture

```
Developer push (main)
        │
        ▼
GitHub Actions ──(OIDC token)──▶ Microsoft Entra ID ──▶ short-lived Azure token
        │
        ├─ docker build ─▶ push image (tagged by commit SHA) ─▶ Azure Container Registry
        │
        └─ az aks get-credentials ─▶ kubectl set image ─▶ rolling update on AKS
                                                              │
                                          LoadBalancer Service (public IP :80)
                                                              │
                                              FastAPI pod (:8000, /health probes)
                                                              │
                              Azure OpenAI  +  Azure AI Search  +  PostgreSQL
```

## Repository layout

| Path | Purpose |
|------|---------|
| `app.py`, `main.py`, `routes/`, `rag/`, `llm/`, `ingestion/`, `vectorstore/`, `database/` | The RAG application |
| `dockerfile` | Container image (Python 3.12-slim, uvicorn on :8000) |
| `k8s/deployment.yaml`, `k8s/service.yaml` | Kubernetes Deployment + LoadBalancer Service |
| `terraform/` | Infrastructure-as-code that provisions the AKS cluster and the AcrPull role assignment |
| `.github/workflows/deploy.yaml` | CI/CD pipeline (build → push → deploy → verify) |
| `CICD_Deployment_Guide.md` | Field-by-field explanation of the manifests and workflow |

## CI/CD pipeline

On every push to `main` (code changes only — docs and Terraform are ignored):

1. **Authenticate to Azure via OIDC.** GitHub's OIDC token is exchanged for an
   Azure access token through a federated credential on an Entra ID app
   registration. Nothing but non-secret IDs live in GitHub.
2. **Build and push** the image to ACR, tagged with the 12-char commit SHA
   (immutable, so rollbacks are exact) plus a moving `:latest`.
3. **Deploy to AKS** with `kubectl set image`, pinning the SHA tag, then wait on
   `kubectl rollout status`. A failed rollout fails the pipeline.

### Why OIDC over a stored service-principal secret

The course uses an `AZURE_CREDENTIALS` JSON blob (a service-principal password)
in a GitHub secret. This repo uses Entra ID federated credentials instead: the
runner gets a fresh, short-lived token per run, there is no password to rotate
or leak, and the trust is scoped to exactly this repo and its `main` branch.

## Configuration and secrets

Application configuration (Azure OpenAI, AI Search, and PostgreSQL credentials)
is supplied to the pod from a Kubernetes Secret named `invint-secrets`, created
out-of-band from a local `.env`. Image-pull credentials for the private registry
live in a `docker-registry` secret named `acr-pull`. **No credentials are ever
committed to git** — `.env`, Terraform state, and `*.tfvars` are all gitignored.

## Local development

```bash
uv pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
# http://localhost:8000  •  docs at /docs  •  health at /health
```

## Infrastructure

The AKS cluster is provisioned with Terraform (`terraform/`). The registry and
resource group are read as data sources, so `terraform destroy` removes only the
cluster and its role assignment — the container image is never touched.

```bash
cd terraform
terraform init
terraform apply
```

---

*The RAG application code originates from Krish Naik's Agentic-AI course. The
Terraform, the corrected Kubernetes manifests, and the OIDC-based CI/CD pipeline
in this repository are original deployment work built on top of it.*
