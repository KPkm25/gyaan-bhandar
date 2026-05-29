# Gyaan Bhandar

> RAG-powered document assistant · Flask + React + FAISS + Groq

Ask questions about your documents in natural language. The backend retrieves the most relevant text chunks using **FAISS** vector search and answers using the **Groq LLaMA 3.1** LLM. All chat sessions and documents are managed locally — no external database required.

---

## Table of Contents

- [Stack](#stack)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Local Development](#local-development)
- [Kubernetes Deployment](#kubernetes-deployment)
  - [Prerequisites](#prerequisites)
  - [Infrastructure Setup](#infrastructure-setup)
  - [Application Deployment](#application-deployment)
  - [Verify Deployment](#verify-deployment)
- [CI/CD Pipeline](#cicd-pipeline)
- [Monitoring](#monitoring)
- [API Reference](#api-reference)
- [Features](#features)
- [Troubleshooting](#troubleshooting)

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Flask-CORS |
| Vector Search | FAISS + sentence-transformers (all-MiniLM-L6-v2) |
| LLM | Groq API (LLaMA 3.1 8b instant) |
| Frontend | React 18, react-markdown, remark-gfm |
| Storage | PersistentVolumeClaims (FAISS index, documents, chat history, model) |
| Orchestration | Kubernetes (K3s) |
| Ingress | NGINX Ingress Controller |
| Load Balancer | MetalLB (bare-metal) |
| Autoscaling | Horizontal Pod Autoscaler + Metrics Server |
| Monitoring | Prometheus + Grafana (kube-prometheus-stack) |
| CI/CD | GitHub Actions (self-hosted runner) |

---

## Project Structure

```
gyaan-bhandar/
├── backend/
│   ├── app.py                    
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example              ← template for environment variables
├── frontend/
│   ├── src/
│   │   ├── App.jsx               
│   │   ├── App.css
│   │   └── index.js
│   ├── nginx.conf                ← Nginx config for the frontend container
│   └── Dockerfile
├── k8s/
│   ├── namespace.yaml
│   ├── secret.template.yaml      
│   ├── Config-maps/
│   │   └── config-map.yaml
│   ├── Volumes/
│   │   └── PVC.yaml              ← faiss-store, chat-history, documents, model
│   ├── Deployment/
│   │   ├── deployment-backend.yaml   
│   │   └── deployment-frontend.yaml
│   ├── Services/
│   │   ├── backend-service.yaml
│   │   ├── frontend-service.yaml
│   │   └── ingress-nginx-service-patch.yaml
│   ├── Ingress/
│   │   └── ingress.yaml
│   ├── HPA/
│   │   └── hpa.yaml
│   ├── MetalLB/
│   │   └── metallb-config.yaml
│   ├── NetworkPolicy/
│   │   └── network-policy.yaml
│   ├── PodDisruptionBudget/
│   │   └── pdb.yaml
│   └── Monitoring/
│       ├── prometheus-grafana-values.yaml
│       └── gyaan-bhandar-dashboard.json
└── .github/
    └── workflows/
        ├── ci.yml
        └── cd.yml
```

---

## Architecture

```
                         ┌─────────────────────────────────────────┐
                         │           VMware / Bare-metal            │
                         │                                          │
  Browser ──────────────►│  MetalLB IP (192.168.1.240)             │
                         │         │                                │
                         │  ┌──────▼──────────────┐                │
                         │  │  NGINX Ingress       │                │
                         │  │  Controller          │                │
                         │  └──────┬───────────────┘                │
                         │         │                                │
                         │    /    │    /api/*                      │
                         │  ┌──────▼──┐   ┌────────────────────┐   │
                         │  │Frontend │   │ Backend            │   │
                         │  │ Service │   │ Service            │   │
                         │  └──────┬──┘   └─────────┬──────────┘   │
                         │         │                 │              │
                         │  ┌──────▼──┐   ┌─────────▼──────────┐   │
                         │  │React    │   │ Flask + FAISS       │   │
                         │  │ Pod(s)  │   │ Pod(s)             │   │
                         │  │HPA:1-3  │   │ HPA: 1-5           │   │
                         │  └─────────┘   └─────────┬──────────┘   │
                         │                           │              │
                         │               ┌───────────▼───────────┐  │
                         │               │  PersistentVolumes     │  │
                         │               │  - faiss-store-pvc     │  │
                         │               │  - documents-pvc       │  │
                         │               │  - chat-history-pvc    │  │
                         │               │  - model-pvc           │  │
                         │               └───────────────────────┘  │
                         │                                          │
                         │  ┌────────────────────────────────────┐  │
                         │  │  monitoring namespace              │  │
                         │  │  Prometheus · Grafana · Alertmgr   │  │
                         │  └────────────────────────────────────┘  │
                         └─────────────────────────────────────────┘
```

**Request flow:**
1. Browser hits `http://gyaan-bhandar.test` → MetalLB routes to NGINX Ingress Controller
2. NGINX routes `/` → frontend Service → React pod (serves static files)
3. React makes API calls to `gyaan-bhandar.test/api/*` → NGINX strips `/api` prefix → backend Service → Flask pod
4. Flask queries FAISS index (on PVC), calls Groq API, returns answer

---

## Local Development

### Backend

```bash
cd backend
pip install -r requirements.txt

# Create .env from template
cp .env.example .env
# Fill in GROQ_API_KEY, MODEL_PATH

python app.py
```

### Frontend

```bash
cd frontend
npm install
npm start     # runs at http://localhost:3000
```

> The frontend dev server proxies API calls to `http://localhost:5000` via the `REACT_APP_API_BASE` env var fallback.

---

## Kubernetes Deployment

> **Environment:** K3s on VMware (or any bare-metal Linux node). No cloud provider required.

### Prerequisites

Install the following on your node before deploying:

#### 1. K3s
```bash
curl -sfL https://get.k3s.io | sh -
# Disable Traefik (we use NGINX instead)
echo "disable: [traefik]" | sudo tee /etc/rancher/k3s/config.yaml
sudo systemctl restart k3s
```

Make kubectl accessible without sudo:
```bash
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
source ~/.bashrc
```

Persist permissions across reboots:
```bash
sudo tee /etc/systemd/system/k3s.service.d/kubeconfig-permissions.conf << 'EOF'
[Service]
ExecStartPost=/bin/chmod 644 /etc/rancher/k3s/k3s.yaml
EOF
sudo systemctl daemon-reload
```

#### 2. Helm
```bash
sudo snap install helm --classic
```

#### 3. NGINX Ingress Controller
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/baremetal/deploy.yaml
```

#### 4. Metrics Server (required for HPA)
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

#### 5. MetalLB (bare-metal LoadBalancer)
```bash
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.5/config/manifests/metallb-native.yaml
kubectl wait --namespace metallb-system \
  --for=condition=ready pod \
  --selector=app=metallb \
  --timeout=90s
```

Edit `k8s/MetalLB/metallb-config.yaml` — set the IP range to an unused range on your LAN:
```yaml
spec:
  addresses:
    - 192.168.1.240-192.168.1.240   # single pinned IP
```

Then apply:
```bash
kubectl apply -f k8s/MetalLB/metallb-config.yaml
```

Patch the NGINX Ingress Controller Service to use MetalLB:
```bash
kubectl apply -f k8s/Services/ingress-nginx-service-patch.yaml
# Verify external IP assigned:
kubectl get svc -n ingress-nginx
```

#### 6. Prometheus + Grafana
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
helm install kube-prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values k8s/Monitoring/prometheus-grafana-values.yaml
```

#### 7. DNS / hosts entry

Add to `/etc/hosts` on the node **and** any machine that needs to access the app:
```
192.168.1.240   gyaan-bhandar.test
```


---

### Infrastructure Setup

These resources are created **once** and are not managed by the CI/CD pipeline. They persist across deployments.

```bash
# 1. Namespace
kubectl apply -f k8s/namespace.yaml

# 2. Secrets 
cp k8s/secret.template.yaml k8s/secrets.yaml
nano k8s/secrets.yaml   # add GROQ_API_KEY, GITHUB_TOKEN, GITHUB_REPO
kubectl apply -f k8s/secrets.yaml

# 3. ConfigMap
kubectl apply -f k8s/Config-maps/config-map.yaml

# 4. PersistentVolumeClaims
kubectl apply -f k8s/Volumes/PVC.yaml
```

Verify:
```bash
kubectl get pvc -n gyaan-bhandar
```

> **Note:** The `all-MiniLM-L6-v2` model (~90MB) is downloaded automatically by an init container on first pod start. Internet access is required on the node for this. Subsequent restarts skip the download as the model is cached in the PVC.

---

### Application Deployment

```bash
kubectl apply -f k8s/Deployment/
kubectl apply -f k8s/Services/
kubectl apply -f k8s/Ingress/
kubectl apply -f k8s/HPA/
kubectl apply -f k8s/PodDisruptionBudget/
kubectl apply -f k8s/NetworkPolicy/
```

Watch pods come up (init container runs first, then main container):
```bash
kubectl get pods -n gyaan-bhandar -w
```

---

### Verify Deployment

```bash
# All pods healthy
kubectl get pods -n gyaan-bhandar

# Services and Ingress
kubectl get svc,ingress -n gyaan-bhandar

# HPA status
kubectl get hpa -n gyaan-bhandar

# Test backend directly
curl http://gyaan-bhandar.test/api/health
# Expected: {"chunks_loaded":0,"documents":0,"status":"ok"}

# Open in browser
http://gyaan-bhandar.test
```

---

## CI/CD Pipeline

The pipeline uses a **self-hosted GitHub Actions runner** on the same node as the cluster.

```
Push to any branch                Push to main
        │                               │
        ▼                               ▼
  ┌─────────────┐               ┌──────────────┐
  │   ci.yml    │   on success  │   cd.yml     │
  │             │──────────────►│              │
  │ • lint      │               │ • kubectl    │
  │ • build     │               │   set image  │
  │ • trivy     │               │ • rollout    │
  │ • push SHA  │               │   status     │
  └─────────────┘               └──────────────┘
```

### Runner Setup

```bash
# Create a dedicated low-privilege user for the runner
sudo useradd -m -s /bin/bash github-runner
sudo usermod -aG docker github-runner

# Copy kubeconfig so runner can access the cluster
sudo mkdir -p /home/github-runner/.kube
sudo cp ~/.kube/config /home/github-runner/.kube/config
sudo chown -R github-runner:github-runner /home/github-runner/.kube

# Install runner — follow exact commands from:
# GitHub repo → Settings → Actions → Runners → New self-hosted runner
sudo su - github-runner
# paste GitHub-provided commands here
```

### GitHub Secrets Required

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | Your DockerHub username |
| `DOCKERHUB_TOKEN` | DockerHub access token (not password) |


### Image Tagging

Images are tagged with the Git SHA, not `latest`:
```
kpkm25/gyan-bhandar-backend:a3f2c1d
kpkm25/gyan-bhandar-frontend:a3f2c1d
```

This ensures every deployment is reproducible and rollbacks are trivial:
```bash
# Rollback to a previous SHA
kubectl set image deployment/gyan-bhandar-backend \
  gyan-bhandar-backend=kpkm25/gyan-bhandar-backend:<previous-sha> \
  -n gyaan-bhandar
```

### Runner Security Considerations

- Runner executes as `github-runner` user, not root
- Workflows only trigger on `push` to protected branches — never on PRs from forks
- Runner has scoped kubeconfig access limited to the `gyaan-bhandar` namespace


---

## Monitoring

Grafana is accessible at `http://<node-ip>:32000`
Default credentials: `admin / admin`

### Available Dashboards

- **Kubernetes Overview** (Grafana ID 15760) — cluster-wide pod health, CPU, memory
- **Gyaan Bhandar** (custom) — request rate, p95 latency, replica count, memory per pod

### Import Custom Dashboard

1. Open Grafana → Dashboards → Import
2. Upload `k8s/Monitoring/gyaan-bhandar-dashboard.json`

### Key Metrics

| Metric | Query |
|---|---|
| Request rate | `rate(flask_http_request_total{namespace="gyaan-bhandar"}[5m])` |
| p95 latency | `histogram_quantile(0.95, rate(flask_http_request_duration_seconds_bucket[5m]))` |
| Backend replicas | `kube_deployment_status_replicas_available{deployment="gyan-bhandar-backend"}` |
| Memory per pod | `container_memory_working_set_bytes{namespace="gyaan-bhandar"}` |

> **Note:** Flask metrics require `prometheus-flask-exporter` in `requirements.txt` and a `/metrics` endpoint in `app.py`. The backend deployment is already annotated for Prometheus scraping.

---

## API Reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/health` | Backend status, chunks loaded, document count |
| `POST` | `/query` | `{ query, session_id }` → answer + retrieved chunks |
| `POST` | `/upload` | Multipart file upload → triggers index rebuild |
| `GET` | `/documents` | List all uploaded documents with size and date |
| `DELETE` | `/documents/<n>` | Delete a document and rebuild the index |
| `POST` | `/rebuild-index` | Force full re-parse and index rebuild |
| `GET` | `/sessions` | List all chat sessions (sorted by recent) |
| `POST` | `/sessions` | Create a new chat session |
| `GET` | `/sessions/<id>` | Get full message history for a session |
| `DELETE` | `/sessions/<id>` | Delete a chat session |

---

## Features

### Document Management
- Upload documents via the UI — index rebuilds automatically
- Collapsible documents panel shows filename, size, and upload date
- Delete documents from the UI — index rebuilds automatically
- Hash-based change detection — index only rebuilds when documents actually change

### Chat & Sessions
- Full chat history stored as JSON on a PVC
- Sidebar lists all past sessions — click any to restore the full conversation
- Sessions are auto-titled from the first message
- Each AI response shows the retrieved source chunks with page numbers
- Copy button on every code block in AI responses

### Index Persistence

```
First run:    documents/ → parse → chunk → embed → faiss.index + chunks.pkl
Later runs:   hash match → load from disk (instant)
New file:     hash mismatch → rebuild index automatically
```

---

## Importing Terraform Docs

```bash
git clone --filter=blob:none --sparse https://github.com/hashicorp/web-unified-docs.git
cd web-unified-docs
git sparse-checkout set content/terraform-docs-common

find content/terraform-docs-common -name "*.mdx" | while read f; do
  relative="${f#content/terraform-docs-common/}"
  newname="${relative//\//_}"
  cp "$f" "../backend/documents/$newname"
done
```

> First index build with many MDX files may take several minutes. Subsequent restarts load from the saved index instantly.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `kubectl` permission denied on k3s.yaml | `sudo chmod 644 /etc/rancher/k3s/k3s.yaml` |
| Backend pod stuck in `Init:0/1` | Check internet access — init container downloads model from HuggingFace |
| 502 Bad Gateway from Ingress | Check NetworkPolicy allows `10.42.0.0/16` CIDR; check backend pod is `1/1 Running` |
| HPA scaling unexpectedly | Check `kubectl describe hpa -n gyaan-bhandar` for metric errors; Metrics Server may still be starting |
| MetalLB IP not assigned (`<pending>`) | Verify IP range doesn't conflict with router DHCP; check `kubectl logs -n metallb-system` |
| Groq API key invalid | Run `kubectl exec -n gyaan-bhandar deploy/gyan-bhandar-backend -- python3 -c "import os; print(repr(os.getenv('groq_key')))"` — check for trailing whitespace |
| Frontend using `localhost:5000` | Image was built without `--build-arg REACT_APP_API_BASE=...`; rebuild with the arg |
| Backend offline (red dot in UI) | Check `kubectl logs -n gyaan-bhandar deploy/gyan-bhandar-backend` |
| Index not updating after upload | The documents PVC may be full; check `kubectl exec` into pod and run `df -h /app/documents` |