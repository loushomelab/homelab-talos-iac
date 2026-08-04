#!/bin/bash
set -e

echo "================================================================"
echo "🚀 Talos Cluster Day-0 Bootstrap Script (ArgoCD + Doppler)"
echo "================================================================"

# 1. 确保 kubectl 可用
if ! command -v kubectl &> /dev/null; then
    echo "❌ Error: kubectl could not be found. Please install it."
    exit 1
fi

echo "✅ kubectl found. Checking cluster connection..."
if ! kubectl get nodes &> /dev/null; then
    echo "❌ Error: Cannot connect to Kubernetes cluster. Have you completed 'talosctl bootstrap' and fetched the kubeconfig?"
    exit 1
fi

# 2. 安装 ArgoCD
echo "📦 Installing ArgoCD core components..."
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 3. 获取 Doppler Token 并注入
echo ""
echo "🔐 Doppler Operator Needs a Service Token to authenticate."
echo "Please go to Doppler -> Your Project -> argocd (or your target config) -> Access -> Service Tokens -> Generate"
read -p "Enter your Doppler Service Token (dp.st...): " DOPPLER_TOKEN

if [ -z "$DOPPLER_TOKEN" ]; then
    echo "❌ Error: Doppler token is required."
    exit 1
fi

echo "Injecting Doppler Token into Kubernetes..."
kubectl create namespace doppler-operator-system --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic doppler-operator-token \
  -n doppler-operator-system \
  --from-literal=dopplerToken="$DOPPLER_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

# 4. 等待 ArgoCD 准备就绪
echo "⏳ Waiting for ArgoCD pods to be ready (this may take a few minutes)..."
kubectl wait --for=condition=Ready pods --all -n argocd --timeout=300s

# 5. 应用 Root App (App of Apps)
echo "🌐 Applying ArgoCD Root App (App of Apps)..."
kubectl apply -n argocd -f bootstrap/root-app.yaml

# 6. 打印初始密码
echo "================================================================"
echo "🎉 Bootstrap Complete!"
echo "ArgoCD will now sync everything from the git repository."
echo ""
echo "🔑 Your initial ArgoCD admin password is:"
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
echo ""
echo "You can temporarily access the UI by port-forwarding:"
echo "kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "Then visit https://localhost:8080"
echo "================================================================"
