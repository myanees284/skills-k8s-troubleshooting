# EKS Kubernetes Troubleshooting Skill

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill for **read-only** Kubernetes and Amazon EKS troubleshooting.

Claude runs small Python scripts that read your local kubeconfig, collect cluster evidence, and return structured JSON. Claude then analyzes that JSON to explain what is wrong and what to do next — without changing your cluster.

## What this project does

- Lists cluster contexts and namespaces from your kubeconfig
- Scans a namespace for unhealthy pods, deployments, and warning events
- Investigates specific pods or all unhealthy resources in a namespace
- Collects logs, events, deployment status, and node details
- Optionally saves investigations to a local JSON history file
- Supports optional deployment context (`context/deployment-context.txt`) so teams can tailor AI advice

Everything is **read-only**. No web UI, Docker, or external AI API is required.

## Who it is for

- Platform and DevOps engineers troubleshooting EKS or other Kubernetes clusters
- SREs who want Claude Code to gather evidence before suggesting fixes
- Teams that already use `kubectl` and want a structured, agent-friendly workflow

You must already have cluster access configured on your machine. This skill does not create credentials for you.

## How it works

1. You ask Claude to troubleshoot a cluster issue.
2. Claude runs scripts from this skill (starting with `list_contexts.py`).
3. Scripts call the Kubernetes API using your existing `~/.kube/config` credentials.
4. Scripts print JSON to stdout (errors go to stderr as JSON).
5. Claude reads the JSON, explains findings, and **suggests** remediation steps.
6. You decide whether to run any fix commands yourself.

See [examples/sample_prompts.md](./examples/sample_prompts.md) for prompt ideas and [examples/](./examples/) for sample JSON output.

## Architecture

```
┌─────────────────┐     runs      ┌──────────────────┐
│   Claude Code   │ ────────────► │  scripts/*.py    │
│   (analysis)    │ ◄──────────── │  (JSON stdout)   │
└────────┬────────┘   parses JSON └────────┬─────────┘
         │ reads (optional)                  │
         ▼                                 ▼
┌─────────────────┐               ┌──────────────────┐
│ deployment-     │               │    skill_lib/    │
│ context.txt     │               │  kube_client     │──► ~/.kube/config
└─────────────────┘               │  health_scanner  │──► Kubernetes API
                                  │  investigator    │
                                  │  history         │──► local JSON file
                                  └──────────────────┘
```

| Component | Role |
|-----------|------|
| `scripts/` | CLI entry points; all output is JSON |
| `context/deployment-context.txt` | Optional org-specific deploy/monitoring notes (user-local) |
| `skill_lib/kube_client.py` | Loads kubeconfig per context; read-only API calls |
| `skill_lib/health_scanner.py` | Namespace health scan and anomaly detection |
| `skill_lib/investigator.py` | Deep evidence collection for pods/namespaces |
| `skill_lib/formatters.py` | Summaries, issue detection, response models |
| `skill_lib/history.py` | Optional local investigation history |
| `SKILL.md` | Instructions Claude Code reads when using this skill |

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.10+ | For running scripts |
| `pip` | To install dependencies |
| Valid kubeconfig | `~/.kube/config` or `KUBECONFIG` env var |
| Cluster credentials | Already working for `kubectl get ns` |
| Claude Code | With this skill installed |

### AWS SSO and kubeconfig setup (EKS)

This skill **does not** run AWS login or modify your kubeconfig. Set up access on your machine first:

```bash
# 1. Authenticate with AWS (example — use your org's method)
aws sso login --profile my-profile

# 2. Add the EKS cluster to kubeconfig (one-time or when cluster changes)
aws eks update-kubeconfig \
  --name demo-eks-cluster \
  --region us-east-1 \
  --profile my-profile

# 3. Verify access
kubectl get namespaces --context <context-from-kubeconfig>
```

For non-EKS clusters (kind, minikube, GKE, AKS), ensure your kubeconfig already points to the cluster and `kubectl` works.

## Installation

```bash
git clone <your-repo-url>
cd eks-kubernetes-troubleshooting-skill

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Install as a Claude Code skill

Copy or symlink this folder into a Claude Code skills directory:

- **Project skill:** `.cursor/skills/eks-kubernetes-troubleshooting/`
- **Personal skill:** `~/.cursor/skills/eks-kubernetes-troubleshooting/`

The folder must contain `SKILL.md`. See [SKILL.md](./SKILL.md) for agent behavior and safety rules.

### Customize AI analysis (optional)

Copy and edit the deployment context template for your org:

```bash
cp context/deployment-context.example.txt context/deployment-context.txt
# edit for your CI/CD, Helm, and monitoring stack — gitignored locally
```

## Usage

Run scripts from the project root. Use `python3` if `python` is not available.

### 1. Discover context and namespace

```bash
python3 scripts/list_contexts.py
python3 scripts/list_namespaces.py --context arn:aws:eks:us-east-1:123456789012:cluster/demo-eks-cluster
```

### 2. Scan namespace health

```bash
python3 scripts/scan_namespace.py \
  --context arn:aws:eks:us-east-1:123456789012:cluster/demo-eks-cluster \
  --namespace staging
```

Example output shape: [examples/sample_namespace_scan_output.json](./examples/sample_namespace_scan_output.json)

### 3. Investigate a pod

```bash
python3 scripts/investigate_pod.py \
  --context arn:aws:eks:us-east-1:123456789012:cluster/demo-eks-cluster \
  --namespace staging \
  --pod web-app-6d4f8b2c1-abc12 \
  --save \
  --root-cause "Missing module in container image" \
  --risk-level Medium
```

Example output shape: [examples/sample_pod_investigation_output.json](./examples/sample_pod_investigation_output.json)

### 4. Investigate all unhealthy resources in a namespace

```bash
python3 scripts/investigate_namespace.py \
  --context arn:aws:eks:us-east-1:123456789012:cluster/demo-eks-cluster \
  --namespace staging
```

### 5. Investigation history (optional)

History is stored locally at `~/.eks-k8s-troubleshooting/history.json`. Override with `K8S_TROUBLESHOOTING_HISTORY_PATH`.

```bash
python3 scripts/save_investigation.py --file investigation.json
python3 scripts/list_investigations.py
python3 scripts/search_investigations.py --q CrashLoopBackOff --namespace staging
python3 scripts/get_investigation.py --id 1
python3 scripts/find_similar_investigations.py --issue-type OOMKilled --namespace staging
```

## Script reference

| Script | Description |
|--------|-------------|
| `list_contexts.py` | List kubeconfig contexts |
| `list_namespaces.py` | List namespaces in a context |
| `scan_namespace.py` | Lightweight health scan |
| `investigate_pod.py` | Evidence for one pod |
| `investigate_namespace.py` | Evidence for unhealthy pods in namespace |
| `save_investigation.py` | Save investigation JSON to history |
| `list_investigations.py` | List saved investigations |
| `search_investigations.py` | Search history |
| `get_investigation.py` | Get full record by ID |
| `find_similar_investigations.py` | Find similar past incidents |

## Optional deployment context

Copy `context/deployment-context.example.txt` to `context/deployment-context.txt` and describe your CI/CD, Helm, and monitoring stack. The agent reads this file when tailoring fix advice. Local copy is gitignored.

## Troubleshooting

| Problem | What to check |
|---------|----------------|
| `kubeconfig_not_found` | File exists at `~/.kube/config` or set `KUBECONFIG` |
| `session_expired` | Re-run AWS SSO login; refresh EKS kubeconfig |
| `permission_denied` | Your Kubernetes RBAC role lacks list/get access |
| `cluster_unreachable` | Cluster API down, VPN required, or stale context |
| `invalid_context` | Run `list_contexts.py` and use an exact context name |
| `invalid_namespace` / `pod_not_found` | Verify namespace and pod name with `list_namespaces.py` |
| `no_unhealthy_resources` | Namespace scan is healthy; use `investigate_pod.py` for a specific pod |
| Script import errors | Run from project root; activate venv; `pip install -r requirements.txt` |

Errors are printed as JSON on stderr, for example:

```json
{
  "status": "error",
  "error_type": "permission_denied",
  "message": "Permission denied accessing Kubernetes resources..."
}
```

## Safety and read-only guarantee

This skill is designed to **observe only**:

- Reads from your local `~/.kube/config` (or `KUBECONFIG`) — it never writes to kubeconfig
- Does **not** perform AWS login, SSO, or credential setup
- Does **not** modify Kubernetes resources
- Does **not** run `apply`, `delete`, `scale`, `restart`, `patch`, `edit`, or equivalent mutating operations
- Uses only Kubernetes **list**, **get**, and **read log** API calls
- Respects whatever RBAC permissions your kubeconfig user already has

Claude should **suggest** remediation steps in plain language or as commands for you to review. Claude must **not** execute fix commands unless you explicitly ask in a separate, intentional step.

Investigation history is stored only on your local machine in a JSON file.

## License

MIT — see [LICENSE](./LICENSE).
