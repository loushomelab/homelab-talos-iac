# ArgoCD IaC for Talos Proxmox Cluster

This repository contains the declarative GitOps infrastructure and application configurations for the Talos Kubernetes cluster.

## Bootstrapping the Cluster (Day 0)

To bootstrap this repository into a fresh Talos cluster, perform the following steps exactly once:

### 1. Install ArgoCD
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 2. Inject Doppler Operator Token
Provide the initial token so the Doppler Operator can fetch the rest of the secrets (e.g., Cloudflare API Token, Authentik keys).
```bash
kubectl create namespace doppler-operator-system
kubectl create secret generic doppler-operator-token \
  -n doppler-operator-system \
  --from-literal=dopplerToken="<YOUR_DOPPLER_TOKEN>"
```

### 3. Apply Root App
Connect ArgoCD to this repository to initiate the automatic sync of all platform components and apps.
```bash
kubectl apply -n argocd -f bootstrap/root-app.yaml
```

### 4. Access ArgoCD
Fetch the initial admin password:
```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
```

## Secrets Management
All application secrets are managed centrally in **Doppler** (Project: `k8s`, Config: `argocd`). 
For example, the Cloudflare integration expects a secret named `CLOUDFLARE_API_TOKEN` to exist in Doppler to provision wildcard certificates.
