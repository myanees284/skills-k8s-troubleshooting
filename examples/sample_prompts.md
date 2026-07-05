# Example prompts for Claude Code

Use these prompts with the [eks-kubernetes-troubleshooting](../SKILL.md) skill installed. Replace placeholder values with your actual context, namespace, and pod names from `list_contexts.py` and `list_namespaces.py`.

## Discovery

- "List the Kubernetes contexts available on my machine."
- "What namespaces exist in context `arn:aws:eks:us-east-1:123456789012:cluster/demo-eks-cluster`?"

## Health scan

- "Run a health scan on namespace `staging` in context `<your-context>` and summarize any issues."
- "Is namespace `payments` healthy? Use the scan script and tell me what is failing."

## Pod investigation

- "Investigate pod `web-app-6d4f8b2c1-abc12` in namespace `staging` and explain why it is crash looping."
- "Collect evidence for pod `api-worker-xyz99` and identify the most likely root cause from logs and events."

## Namespace investigation

- "Something is wrong in namespace `staging`. Investigate all unhealthy resources and give me a root cause analysis."
- "Run a namespace investigation on `staging`, save the result, and suggest fixes — but do not apply any changes."

## History and recurring incidents

- "Search my investigation history for past `OOMKilled` issues in namespace `staging`."
- "Have we seen this CrashLoopBackOff pattern before? Check similar investigations."
- "Save this investigation with root cause 'missing ConfigMap volume mount' and risk level Medium."

## Remediation (suggest only)

- "Based on the investigation and our deployment context, what kubectl commands would fix this? List them for my review — do not run them."
- "Suggest a rollout fix for the deployment replica mismatch. Do not modify the cluster."

## Using deployment context

- "Read context/deployment-context.txt, then analyze the investigation JSON and summarize root cause."
- "Tailor your suggested fix to our GitLab + Helm pipeline described in deployment-context.txt."

## What Claude should not do without explicit approval

- Run `kubectl apply`, `delete`, `scale`, `rollout restart`, `patch`, or `edit`
- Run `aws sso login` or change kubeconfig
- Assume cluster names, namespaces, or credentials — always discover them first
