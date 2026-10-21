#!/usr/bin/env bash
# Installs ArgoCD v2.11.2, pins it to skywatch-worker and deploys the skywatch Application.
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="${KUBECONFIG:-$(pwd)/kubeconfig}"

ARGOCD_VERSION=v2.11.2
NODE_SELECTOR='{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"skywatch-worker"}}}}}'

kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd --server-side \
  -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"

kubectl patch svc argocd-server -n argocd \
  -p '{"spec":{"type":"NodePort","ports":[{"name":"https","port":443,"targetPort":8080,"nodePort":30081}]}}'

for deploy in argocd-server argocd-repo-server argocd-applicationset-controller \
              argocd-dex-server argocd-notifications-controller argocd-redis; do
  kubectl patch deployment "$deploy" -n argocd -p "$NODE_SELECTOR"
done
kubectl patch statefulset argocd-application-controller -n argocd -p "$NODE_SELECTOR"

kubectl apply -f argocd/application.yaml

echo "ArgoCD admin password:"
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
