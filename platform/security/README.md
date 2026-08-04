# Doppler Secret and Reflector Deployment (Day 0 Setup)

Because ArgoCD synchronizes resources asynchronously but depends on external secrets immediately (like Cloudflare tokens), there is a Day-0 bootstrapping caveat. 

**Steps for initial setup:**

1. The `doppler-operator-token` Secret needs to be manually created in the `doppler-operator-system` namespace to authorize Doppler's access.
2. We use `reflector` to mirror this secret to `cert-manager` so that Doppler can synchronize `cloudflare-secret` there.
3. Apply the initial secret to `doppler-operator-system`:
```bash
cat << 'EOT' | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: doppler-operator-token
  namespace: doppler-operator-system
  annotations:
    reflector.v1.k8s.emberstack.com/reflection-allowed: "true"
    reflector.v1.k8s.emberstack.com/reflection-auto-enabled: "true"
    reflector.v1.k8s.emberstack.com/reflection-auto-namespaces: cert-manager
type: Opaque
data:
  # Base64 encoded doppler token (must be named `serviceToken`, not `dopplerToken`)
  serviceToken: <YOUR_BASE64_TOKEN>
EOT
```
*(Ensure the data key is `serviceToken` so Doppler accepts it)*

4. Once applied, Reflector will copy the secret to `cert-manager`.
5. ArgoCD will deploy `DopplerSecret` (named `cloudflare-secret`) configured with `config: prd_argocd`.
6. Doppler Operator will synchronize this secret, enabling Cert-Manager to solve DNS challenges with Cloudflare.

