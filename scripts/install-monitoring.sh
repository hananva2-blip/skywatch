#!/usr/bin/env bash
# Installs kube-prometheus-stack. The CRDs are applied one by one with server-side apply
# first, because a single helm install times out on the t3.micro API server.
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="${KUBECONFIG:-$(pwd)/kubeconfig}"

BASE=https://raw.githubusercontent.com/prometheus-community/helm-charts/main/charts/kube-prometheus-stack/charts/crds/crds
for crd in crd-alertmanagerconfigs crd-alertmanagers crd-podmonitors crd-probes \
           crd-prometheusagents crd-prometheuses crd-prometheusrules \
           crd-scrapeconfigs crd-servicemonitors crd-thanosrulers; do
  kubectl apply --server-side --request-timeout=3m -f "${BASE}/${crd}.yaml"
  sleep 10
done

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update prometheus-community
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --skip-crds \
  -f helm/monitoring/values.yaml
