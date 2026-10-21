# SkyWatch

A small distributed weather-query pipeline, built end to end: application code, tests, CI/CD, infrastructure as code and monitoring.

A Flask frontend takes a city name and publishes a job to RabbitMQ; a worker consumes the queue, looks the city up in the free [Open-Meteo](https://open-meteo.com) API and replies with the current weather, which the frontend shows to the user. Everything runs on a self-provisioned K3s cluster on AWS.

```mermaid
flowchart LR
    U[User] -->|HTTP :30080| F[Frontend<br/>Flask]
    F -->|publish| Q[(RabbitMQ<br/>weather_queries)]
    Q -->|consume| W[Worker x2]
    W -->|HTTPS| O[Open-Meteo API]
    W -.->|reply-to| F
    P[Prometheus] -.->|/metrics| F
    P -.->|:15692| Q
```

## Stack

| Area | Tools |
|---|---|
| Application | Python 3.11, Flask, pika (RabbitMQ) |
| Testing | pytest, pytest-mock |
| CI/CD | GitHub Actions, GHCR, flake8 |
| Infrastructure | Terraform (AWS EC2), Ansible, K3s |
| Deployment | Helm, ArgoCD (GitOps) |
| Observability | kube-prometheus-stack: Prometheus + Grafana (`prometheus-flask-exporter`, ServiceMonitors) |

## Repository layout

```
app/frontend/   Flask web app: form, /query, /healthz, /metrics
app/worker/     RabbitMQ consumer with reconnect/retry loop
tests/          pytest unit tests for the frontend
helm/skywatch/  Helm chart: frontend, worker, RabbitMQ, ingress, ServiceMonitors
terraform/      AWS infra: security group, 3 EC2 nodes, generated Ansible inventory
ansible/        Installs K3s master and joins the worker nodes
.github/        CI/CD pipeline
```

## CI/CD pipeline

On every push and pull request to `main`:

1. **Lint**: flake8 on the frontend and worker.
2. **Test**: pytest suite (RabbitMQ is mocked).
3. **Build & push** (on push to `main` only): builds both Docker images and pushes them to GHCR, tagged with the short commit SHA.
4. **GitOps tag bump**: updates the image tags in `helm/skywatch/values.yaml` and commits back with `[skip ci]`, so the chart always points to an immutable, traceable image.

## Tests

`tests/test_frontend.py` covers:

- the `/healthz` endpoint used by Kubernetes probes
- a successful query: the job is published to the durable queue with a reply-to address and the worker's reply is returned
- input validation: an empty or whitespace-only city returns `400`
- unknown city `404`, worker timeout `504`, RabbitMQ connection error `500`

`tests/test_worker.py` covers the Open-Meteo lookup (mocked HTTP), unknown cities, API failures, and that the worker replies and acks (or nacks bad messages).

```bash
pip install -r app/frontend/requirements.txt -r app/worker/requirements.txt pytest pytest-mock
pytest -v
```

## Deploy

All nodes are `t3.micro` (free tier). K3s is pinned to `v1.29.5+k3s1`, every node gets 2 GB swap, Traefik is disabled and the master is tainted `NoSchedule`.

| Node | Workloads |
|---|---|
| skywatch-master | K3s control plane only |
| skywatch-worker | ArgoCD |
| skywatch-worker2 | SkyWatch app, Prometheus, Grafana |

```bash
# 1. Provision 3 EC2 nodes and generate the Ansible inventory
cd terraform && terraform init && terraform apply

# 2. Install K3s, swap and join the workers (writes ./kubeconfig)
cd ../ansible && ansible-playbook -i inventory.ini playbook.yml
cd .. && export KUBECONFIG=$(pwd)/kubeconfig

# 3. Monitoring (CRDs first, then the chart with helm/monitoring/values.yaml)
./scripts/install-monitoring.sh

# 4. ArgoCD, pinned to skywatch-worker, then the skywatch Application (auto-sync from Git)
./scripts/install-argocd.sh

# 5. At the end of the session, stay in the free tier
cd terraform && terraform destroy
```

| Service | URL |
|---|---|
| SkyWatch | `http://<worker2-ip>:30080` |
| ArgoCD | `https://<any-node-ip>:30081` (admin / printed by the script) |
| Grafana | `http://<worker2-ip>:30030` |
| RabbitMQ management | `kubectl port-forward svc/rabbitmq -n skywatch 15672:15672` |
