#!/bin/bash
# Get logs from Railway and Vercel deployments
# Usage: ./scripts/get_logs.sh [railway|vercel] [lines]

RAILWAY_TOKEN="4db8e47f-11e3-45a5-9314-90d55f05c504"
VERCEL_TOKEN="k4DXJemVS2G9G3zIOgZ4iQcg"

# Railway service IDs
RAILWAY_PROJECT_ID="af7672fd-2a05-49cb-862a-ea4ee201aebe"
RAILWAY_SERVICE_ID="e54d8649-b1c2-400e-9c6c-0e49da7fa381"

LINES=${2:-50}

get_railway_logs() {
    # Get latest deployment ID
    DEPLOYMENT_ID=$(curl -s -H "Authorization: Bearer $RAILWAY_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST https://backboard.railway.app/graphql/v2 \
        -d "{\"query\": \"query { deployments(first: 1, input: { serviceId: \\\"$RAILWAY_SERVICE_ID\\\" }) { edges { node { id status } } } }\"}" \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['deployments']['edges'][0]['node']['id'])")

    echo "Railway logs (deployment: $DEPLOYMENT_ID):"
    echo "============================================"

    curl -s -H "Authorization: Bearer $RAILWAY_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST https://backboard.railway.app/graphql/v2 \
        -d "{\"query\": \"query { deploymentLogs(deploymentId: \\\"$DEPLOYMENT_ID\\\", limit: $LINES) { message timestamp } }\"}" \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
for log in data.get('data', {}).get('deploymentLogs', []):
    ts = log.get('timestamp', '')[:19]
    msg = log.get('message', '')
    print(f'{ts} {msg}')
"
}

get_vercel_logs() {
    echo "Vercel recent deployments:"
    echo "=========================="

    curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
        "https://api.vercel.com/v6/deployments?limit=5" \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
for d in data.get('deployments', []):
    state = d.get('state', d.get('readyState', 'UNKNOWN'))
    msg = d.get('meta', {}).get('githubCommitMessage', 'N/A')[:60]
    uid = d.get('uid', '')
    print(f'{state:10} {uid} - {msg}')
"
}

case "$1" in
    railway|r)
        get_railway_logs
        ;;
    vercel|v)
        get_vercel_logs
        ;;
    *)
        echo "Usage: $0 [railway|vercel] [lines]"
        echo ""
        echo "Examples:"
        echo "  $0 railway 100    # Get last 100 lines from Railway"
        echo "  $0 vercel         # Get Vercel deployment status"
        ;;
esac
