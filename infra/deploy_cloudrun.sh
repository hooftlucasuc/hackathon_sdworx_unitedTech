#!/usr/bin/env bash
# Deploy backend, luisteraar en dashboard naar Cloud Run (europe-west1), alle drie tegelijk.
# Draai in Cloud Shell vanuit de repo-root, na infra/gcp_setup.sh:
#   ./infra/deploy_cloudrun.sh
#   ./infra/deploy_cloudrun.sh backend        # alleen één of meer: backend, listener, frontend
# De ElevenLabs API-key gaat naar Secret Manager (elevenlabs-api-key); het script vraagt erom als
# het secret nog niet bestaat. MIN_INSTANCES=0 maakt de backend goedkoper maar geeft een koude start.
set -euo pipefail

P="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
: "${P:?zet GCP_PROJECT}"
REGION=europe-west1
RUNTIME="callsight-backend@${P}.iam.gserviceaccount.com"
DEPLOYER="projects/${P}/serviceAccounts/callsight-deployer@${P}.iam.gserviceaccount.com"
KEY_SECRET=elevenlabs-api-key
if [ $# -gt 0 ]; then TARGETS=("$@"); else TARGETS=(backend listener frontend); fi

# Cloud Run-URL's zijn voorspelbaar (service-projectnummer.regio.run.app): zo kan elke service de
# andere al kennen voordat die bestaat, en bouwen ze parallel.
PN="$(gcloud projects describe "$P" --format='value(projectNumber)')"
url() { printf 'https://%s-%s.%s.run.app' "$1" "$PN" "$REGION"; }
BACKEND="$(url callsight-backend)"
LISTENER="$(url callsight-listener)"
DASHBOARD="$(url callsight-dashboard)"

say() { printf '\n==> %s\n' "$*"; }

say "Secret $KEY_SECRET"
if ! gcloud secrets describe "$KEY_SECRET" --project="$P" >/dev/null 2>&1; then
  if [ -z "${ELEVENLABS_API_KEY:-}" ]; then
    read -rsp "   ElevenLabs API-key (sk_..., wordt niet getoond): " ELEVENLABS_API_KEY
    echo
  fi
  gcloud secrets create "$KEY_SECRET" --project="$P" --replication-policy=user-managed --locations="$REGION"
  printf '%s' "$ELEVENLABS_API_KEY" | gcloud secrets versions add "$KEY_SECRET" --project="$P" --data-file=-
else
  echo "   bestaat al (nieuwe key: printf '%s' 'sk_...' | gcloud secrets versions add $KEY_SECRET --data-file=-)"
fi
gcloud secrets add-iam-policy-binding "$KEY_SECRET" --project="$P" \
  --member="serviceAccount:$RUNTIME" --role=roles/secretmanager.secretAccessor --quiet >/dev/null

subs_for() {
  case "$1" in
    backend) printf '^@^_FRONTEND_ORIGIN=%s,http://localhost:5173@_MIN_INSTANCES=%s' "$DASHBOARD" "${MIN_INSTANCES:-1}" ;;
    listener) printf '_FORWARD_URL=%s/demo/simulate-call' "$BACKEND" ;;
    frontend) printf '^@^_DATA_SOURCE=api@_API_BASE=%s@_LISTENER_URL=%s' "$BACKEND" "$LISTENER" ;;
    *) echo "onbekend doel: $1 (backend, listener, frontend)" >&2; return 1 ;;
  esac
}

submit() {
  local log="/tmp/callsight-build-$1.log" start=$SECONDS
  if gcloud builds submit --project="$P" --region="$REGION" --config="infra/cloudbuild.$1.yaml" \
      --service-account="$DEPLOYER" --substitutions="$(subs_for "$1")" . >"$log" 2>&1; then
    echo "   $1 klaar in $((SECONDS - start)) s"
  else
    echo "   $1 MISLUKT na $((SECONDS - start)) s: tail -40 $log"
    return 1
  fi
}

say "Bouwen en deployen: ${TARGETS[*]} (parallel, logs in /tmp/callsight-build-*.log)"
pids=()
for t in "${TARGETS[@]}"; do
  subs_for "$t" >/dev/null
  submit "$t" &
  pids+=($!)
done
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done

say "Controle"
curl -fsS "$BACKEND/health" && echo || echo "   backend /health antwoordt (nog) niet"

cat <<EOF

Dashboard              $DASHBOARD
Luisteraar medewerker  $LISTENER/medewerker
Luisteraar beller      $LISTENER/beller
Backend                $BACKEND   (API: $BACKEND/docs)

Open beide luisteraars via de knoppen in de kop van het dashboard: dan delen ze één gesprek-id.
EOF
exit "$failed"
