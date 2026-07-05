---
name: eks-kubernetes-troubleshooting
description: >-
  Read-only Kubernetes/EKS troubleshooting using local kubeconfig. Lists contexts
  and namespaces, scans namespace health, collects pod/namespace investigation
  evidence (logs, events, deployments, nodes) as JSON, and searches local history.
  Use when diagnosing cluster issues, CrashLoopBackOff, OOMKilled, deployment failures,
  pod crashes, or when the user asks to investigate EKS/Kubernetes namespaces or pods.
---

# EKS Kubernetes Troubleshooting

Read-only troubleshooting for clusters reachable via `~/.kube/config`. Scripts use the official Kubernetes Python client with `config.load_kube_config(context=context_name)`. They never modify the cluster, kubeconfig, or cloud credentials.

## When to use this skill

Use this skill when the user:

- Reports Kubernetes or EKS problems (pods failing, deployments unavailable, restarts, OOM, image pull errors)
- Asks to investigate a namespace, pod, deployment, or cluster health
- Wants structured evidence before root cause analysis
- Mentions `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, replica mismatches, or warning events
- Wants to compare a current incident with past investigations

Do **not** use this skill for:

- Applying fixes, scaling, deleting, or restarting resources (suggest only — see Safety)
- AWS login, kubeconfig setup, or IAM changes (tell the user to do that manually)
- Non-Kubernetes infrastructure (unless as supporting context only)

## Prerequisites

Before running scripts:

```bash
cd eks-kubernetes-troubleshooting-skill
pip install -r requirements.txt
```

The user must already have a working kubeconfig and cluster access (`kubectl get ns` succeeds). For EKS, the user handles `aws sso login` and `aws eks update-kubeconfig` themselves — this skill does not.

## How to run scripts

1. Run from the skill project root: `eks-kubernetes-troubleshooting-skill/`
2. Prefer `python3 scripts/<name>.py` (use `python` if that is the user's default)
3. Pass `--context`, `--namespace`, and `--pod` from discovery or user input — never hardcode cluster names
4. Parse **stdout** as JSON; parse **stderr** as JSON on failure (exit code 1)
5. Do not pipe output through tools that strip structure unless the user asks

### Standard workflow

Unless the user already provided context/namespace/pod:

```bash
python3 scripts/list_contexts.py
python3 scripts/list_namespaces.py --context <context>
python3 scripts/scan_namespace.py --context <context> --namespace <namespace>
```

Then investigate:

```bash
# All unhealthy resources in namespace
python3 scripts/investigate_namespace.py --context <context> --namespace <namespace>

# Single pod (including healthy pods the user names explicitly)
python3 scripts/investigate_pod.py --context <context> --namespace <namespace> --pod <pod>
```

Optional: `--tail-lines 200` (default 100). Add `--save` plus `--executive-summary`, `--root-cause`, `--suggested-actions`, `--risk-level` to persist findings locally.

### History commands

```bash
python3 scripts/list_investigations.py
python3 scripts/search_investigations.py --q OOMKilled --namespace staging
python3 scripts/get_investigation.py --id 3
python3 scripts/find_similar_investigations.py --issue-type CrashLoopBackOff --namespace staging
python3 scripts/save_investigation.py --file investigation.json --root-cause "..."
```

Default history file: `~/.eks-k8s-troubleshooting/history.json` (override: `K8S_TROUBLESHOOTING_HISTORY_PATH`).

## Script reference

| Script | Purpose | Key output |
|--------|---------|------------|
| `list_contexts.py` | Kubeconfig contexts | `contexts[]`, `current_context` |
| `list_namespaces.py` | Namespaces in cluster | `namespaces[]` |
| `scan_namespace.py` | Quick health scan | `status`, `issues[]`, `summary` |
| `investigate_namespace.py` | Evidence for unhealthy pods | `evidence`, `ai_reasoning_context` |
| `investigate_pod.py` | Evidence for one pod | `evidence.pods`, `evidence.logs`, `evidence.events` |
| `save_investigation.py` | Save JSON to history | `saved_to_history.id` |
| `list_investigations.py` | List saved records | `investigations[]` |
| `search_investigations.py` | Filter/search history | `investigations[]` |
| `get_investigation.py` | Full record by ID | `investigation`, notes fields |
| `find_similar_investigations.py` | Similar past incidents | `similar_investigations[]` |

See [examples/](./examples/) for sample JSON output.

## Optional deployment context

Teams can tailor fix and prevention advice without changing code:

```bash
cp context/deployment-context.example.txt context/deployment-context.txt
# edit for your org — local copy is gitignored
```

Before writing root cause analysis or suggested fixes, read `context/deployment-context.txt` if it exists. Tailor recommendations to that file — do not recommend tools absent from it.

## How to interpret JSON output

### Success vs error

- **Success:** valid JSON on stdout
- **Error:** JSON on stderr with `status: "error"`, `error_type`, and `message`

Common `error_type` values: `kubeconfig_not_found`, `invalid_context`, `session_expired`, `permission_denied`, `cluster_unreachable`, `invalid_namespace`, `pod_not_found`, `no_unhealthy_resources`.

### Health scan (`scan_namespace.py`)

| Field | Meaning |
|-------|---------|
| `status` | `healthy` or `anomaly` |
| `message` | `We are good here` or `Anomaly detected` |
| `summary` | Counts of pods, deployments, warning events |
| `issues[]` | Each item: `severity`, `type`, `resource_kind`, `resource_name`, `message` |

Start with `issues[]` when `status` is `anomaly`. Common types: `CrashLoopBackOff`, `OOMKilled`, `DeploymentReplicaMismatch`, `HighRestartCount`.

### Investigation output

Read in this order:

1. **`ai_reasoning_context.evidence_summary`** — compact index (issue types, affected pods, OOM/restart hints)
2. **`evidence.namespace_health`** — scope and issue list
3. **`evidence.pods`** — container state, restarts, exit codes, resource limits
4. **`evidence.logs`** — log text plus `detected_patterns` (OOM, errors, module not found)
5. **`evidence.events`** — Kubernetes warning events
6. **`evidence.deployments`** — replica counts and rollout conditions
7. **`evidence.nodes`** — node readiness for affected pods
8. **`evidence.oom_investigations`** — OOM-specific details when present

**Rules for analysis:**

- Read `context/deployment-context.txt` before analysis if it exists
- Base conclusions only on fields present in the JSON — do not invent infrastructure details unless they appear in the evidence
- Structure explanations with **Observed** (facts from evidence), **Correlated** (plausible but unproven), and **Unknown** (missing data)
- If root cause cannot be confirmed, say so and list missing evidence under Unknown
- Cite specific pod names, log lines, event messages, and exit codes
- Note `missing_evidence` entries in `evidence_summary` — do not invent metrics or configs that were not collected
- If logs are empty, say so; do not assume the container was healthy
- Suggest remediation only — never execute mutating commands unless the user explicitly asks

## Safety rules (mandatory)

### What this skill does

- Reads `~/.kube/config` (or `KUBECONFIG`) locally
- Uses the user's existing Kubernetes RBAC permissions
- Performs read-only API operations: list, get, read logs
- Writes only to local investigation history JSON (when `--save` or `save_investigation.py` is used)

### What this skill does NOT do

- AWS SSO login, `aws eks update-kubeconfig`, or any credential provisioning
- Modify kubeconfig or switch the user's default context on disk
- Create, update, delete, scale, restart, patch, or edit Kubernetes resources
- Run mutating `kubectl` commands

### Remediation policy

When the user asks for fixes:

1. **Suggest** remediation steps in plain language
2. Optionally show example `kubectl` or manifest commands **for the user to review**
3. **Do not execute** apply/delete/scale/restart/patch/edit commands unless the user explicitly requests execution in a separate, clear instruction (e.g. "run kubectl apply for me")

Treat all fix commands as proposals. The user runs them manually unless they explicitly delegate execution.

### Other rules

- Never hardcode cluster names, AWS account IDs, namespaces, or secrets
- On `session_expired` or `permission_denied`, tell the user to refresh credentials or fix RBAC — do not retry blindly
- Search investigation history before re-investigating recurring issues

## Example session

```bash
python3 scripts/list_contexts.py
python3 scripts/list_namespaces.py --context arn:aws:eks:us-east-1:123456789012:cluster/demo-eks-cluster
python3 scripts/scan_namespace.py --context arn:aws:eks:us-east-1:123456789012:cluster/demo-eks-cluster --namespace staging
python3 scripts/investigate_pod.py --context arn:aws:eks:us-east-1:123456789012:cluster/demo-eks-cluster --namespace staging --pod web-app-6d4f8b2c1-abc12 --save
```

After investigation, summarize for the user: what failed, likely root cause, suggested next steps, and what evidence is still missing.

## Out of scope

- Web UI, Docker, FastAPI server
- External AI APIs — Claude Code performs analysis from script JSON
- Mutating cluster operations
