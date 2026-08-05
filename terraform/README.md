# AKS infrastructure (Terraform)

The instructor's `deployment-Document.md` starts at Step 7 (`az aks get-credentials`)
and assumes the AKS cluster already exists. It never shows how the cluster was
created. This Terraform fills that gap: it provisions the AKS cluster the doc
depends on, using Infrastructure as Code instead of clicking through the portal.

## What it creates

| Resource | Detail |
|----------|--------|
| AKS cluster | `inv-intelligence-aks`, SystemAssigned managed identity |
| Node pool | 1 x `Standard_B2s` (2 vCPU) — fits the Azure-for-Students 6-vCPU cap |
| Role assignment | AcrPull for the cluster's kubelet identity on the existing ACR |

## What it does NOT touch (referenced as data sources)

- The resource group `rag-inv-intelligence` (already exists)
- The ACR `inveintelligence` and the `invint:v1` image inside it

Because these are `data` sources, `terraform destroy` tears down only the cluster
and the role assignment. Your registry and image survive.

## Constraints baked in

Azure for Students in `spaincentral`:

- Total Regional vCPUs limit: **6**. One `Standard_B2s` node uses 2. Safe.
- Region matches the ACR (`spaincentral`) so image pulls stay in-region.

## Deploy

```bash
cd terraform
terraform init
terraform plan      # review; should show ~2 resources to add
terraform apply     # type yes

# point kubectl at the new cluster (terraform prints this command as an output)
az aks get-credentials --resource-group rag-inv-intelligence --name inv-intelligence-aks --overwrite-existing
kubectl get nodes   # STATUS should be Ready

# create the secret the deployment expects (envFrom: invint-secrets)
# from the app .env file, then deploy the corrected manifests:
kubectl create secret generic invint-secrets --from-env-file=../.env
kubectl apply -f k8s-deployment.yaml
kubectl apply -f k8s-service.yaml

kubectl get pods -w        # wait for Running
kubectl get svc invint     # wait for EXTERNAL-IP, then open http://<ip>
```

## Corrected manifests

`k8s-deployment.yaml` here fixes two bugs in `../k8s/deployment.yaml`:

- registry `invintelligence` -> `inveintelligence` (the real ACR name)
- tag `latest` -> `v1` (the tag actually in ACR)

Without those fixes the pod fails with `ImagePullBackOff`.

## Tear down

```bash
terraform destroy   # removes only the AKS cluster + role assignment
```
