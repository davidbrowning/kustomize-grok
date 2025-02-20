#!/usr/bin/env python3
import sys
import yaml
from collections import defaultdict

# Read input YAML file
if len(sys.argv) != 2:
    print("Usage: python my_tool.py <kustomize_output.yaml>")
    sys.exit(1)

input_file = sys.argv[1]
with open(input_file, 'r') as f:
    docs = list(yaml.safe_load_all(f))

# Collect resources by kind and (namespace, name)
resources = defaultdict(dict)
for doc in docs:
    if not doc or 'kind' not in doc or 'metadata' not in doc:
        continue
    kind = doc['kind']
    metadata = doc['metadata']
    name = metadata.get('name')
    namespace = metadata.get('namespace', 'default')
    resources[kind][(namespace, name)] = doc

# Helper to find a deployment's associated service
def find_associated_service(deployment):
    selector = deployment['spec'].get('selector', {}).get('matchLabels', {})
    namespace = deployment['metadata'].get('namespace', 'default')
    for (svc_ns, svc_name), svc in resources['Service'].items():
        if svc_ns == namespace and svc['spec'].get('selector') == selector:
            return svc_ns, svc_name, svc
    return None, None, None

# Analyze and build report
report = "# Deployment Analysis Report\n\n"
for (ns, name), deployment in resources['Deployment'].items():
    report += f"## Deployment: {ns}/{name}\n\n"

    # Outgoing Connections
    report += "### Outgoing Connections\n\n"
    containers = deployment['spec']['template']['spec'].get('containers', [])
    for container in containers:
        env = container.get('env', [])
        for env_var in env:
            value = env_var.get('value', '')
            if 'svc.cluster.local' in value or '://' in value:
                report += f"- **Endpoint**: `{value}`\n"
                # Extract port if possible
                port = None
                if '://' in value and ':' in value.split('://')[1]:
                    port_part = value.split('://')[1].split(':')[-1].split('/')[0]
                    if port_part.isdigit():
                        port = port_part
                elif 'svc.cluster.local' in value:
                    svc_name = value.split('.')[0]
                    svc_ns = value.split('.')[1] if len(value.split('.')) > 1 else ns
                    svc = resources['Service'].get((svc_ns, svc_name))
                    if svc and svc['spec'].get('ports'):
                        port = svc['spec']['ports'][0].get('port')
                if port:
                    report += f"  - **Port**: {port}\n"
                # Network path via Istio
                if 'svc.cluster.local' in value:
                    svc_name = value.split('.')[0]
                    for (dr_ns, dr_name), dr in resources['DestinationRule'].items():
                        if dr['spec'].get('host') == value or dr['spec'].get('host') == svc_name:
                            report += f"  - **Istio DestinationRule**: {dr_ns}/{dr_name} (e.g., loadBalancer: {dr['spec'].get('trafficPolicy', {}).get('loadBalancer', 'N/A')})\n"
                elif '://' in value:
                    host = value.split('://')[1].split(':')[0].split('/')[0]
                    for (se_ns, se_name), se in resources['ServiceEntry'].items():
                        if se['spec'].get('hosts', []) and host in se['spec']['hosts']:
                            report += f"  - **Istio ServiceEntry**: {se_ns}/{se_name}\n"
                report += "\n"

    # Incoming Traffic
    report += "### Incoming Traffic\n\n"
    svc_ns, svc_name, svc = find_associated_service(deployment)
    if svc:
        report += f"- **Service**: {svc_ns}/{svc_name}\n"
        ports = svc['spec'].get('ports', [])
        for port in ports:
            report += f"  - **Port**: {port.get('port')}\n"
        # VirtualService and Gateway
        for (vs_ns, vs_name), vs in resources['VirtualService'].items():
            for route in vs['spec'].get('http', []):
                dest = route.get('route', [{}])[0].get('destination', {})
                if dest.get('host') == svc_name and (vs_ns == svc_ns or not dest.get('subset')):
                    report += f"  - **VirtualService**: {vs_ns}/{vs_name} (e.g., route to {svc_name})\n"
                    for gw in vs['spec'].get('gateways', []):
                        gw_key = (svc_ns, gw) if '/' not in gw else tuple(gw.split('/'))
                        if gw_key in resources['Gateway']:
                            report += f"    - **Gateway**: {gw}\n"

    # Service Mesh Role
    report += "### Service Mesh Role\n\n"
    sidecar_found = False
    for (sc_ns, sc_name), sc in resources['Sidecar'].items():
        if sc_ns == ns:
            report += f"- **Sidecar**: {sc_ns}/{sc_name} (e.g., egress hosts: {sc['spec'].get('egress', [{}])[0].get('hosts', 'N/A')})\n"
            sidecar_found = True
    if not sidecar_found:
        report += "- No specific Sidecar configuration found for this namespace.\n"

    report += "\n"

# Write report to stdout (or could write to a file)
print(report)