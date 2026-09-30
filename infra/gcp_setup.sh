#!/usr/bin/env bash
# One-time Google Cloud + Firebase setup for CallSight. Everything in europe-west1.
# Idempotent: every create step tolerates "already exists".
#
# Usage:
#   gcloud auth login && gcloud auth application-default login
#   GCP_PROJECT=<project-from-builderbase> ./infra/gcp_setup.sh
#
# Optional: ELEVENLABS_WEBHOOK_SECRET / ELEVENLABS_API_KEY in the environment are stored
# as a new Secret Manager version. Nothing is written to disk; no service-account keys.
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"
REGION="${GCP_REGION:-europe-west1}"
EMBEDDING_DIM="${EMBEDDING_DIM:-768}"
SA_NAME=callsight-backend
SA="${SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

step() { printf '\n==> %s\n' "$*"; }

step "Project en API's"
gcloud config set project "$GCP_PROJECT"
gcloud services enable \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  firebase.googleapis.com \
  identitytoolkit.googleapis.com

step "Firestore Native in $REGION"
gcloud firestore databases create --location="$REGION" --type=firestore-native 2>/dev/null \
  || echo "Firestore (default) bestaat al"
gcloud firestore databases describe --database='(default)' --format='value(locationId)'

step "Service account voor Cloud Run"
gcloud iam service-accounts create "$SA_NAME" --display-name="CallSight backend" 2>/dev/null \
  || echo "service account bestaat al"
for role in roles/datastore.user roles/aiplatform.user roles/secretmanager.secretAccessor roles/firebaseauth.viewer; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
    --member="serviceAccount:$SA" --role="$role" --condition=None --quiet >/dev/null
done
echo "rollen toegekend aan $SA"

step "Secrets (Secret Manager, replicatie $REGION)"
for secret in elevenlabs-webhook-secret elevenlabs-api-key; do
  gcloud secrets create "$secret" --replication-policy=user-managed --locations="$REGION" 2>/dev/null \
    || echo "secret $secret bestaat al"
done
if [ -n "${ELEVENLABS_WEBHOOK_SECRET:-}" ]; then
  printf '%s' "$ELEVENLABS_WEBHOOK_SECRET" | gcloud secrets versions add elevenlabs-webhook-secret --data-file=-
fi
if [ -n "${ELEVENLABS_API_KEY:-}" ]; then
  printf '%s' "$ELEVENLABS_API_KEY" | gcloud secrets versions add elevenlabs-api-key --data-file=-
fi

step "Firestore-indexen (bouwen duurt een paar minuten)"
# Vector search op de kennisbank. Geen prefilter: category wordt niet uitgesloten (TEAMPLAN §1.5).
gcloud firestore indexes composite create --collection-group=solutions --query-scope=COLLECTION \
  --field-config=vector-config="{\"dimension\":\"${EMBEDDING_DIM}\",\"flat\":\"{}\"}",field-path=problem_embedding \
  2>/dev/null || echo "vector-index solutions bestaat al"
# Dashboard: historie per beller en per bedrijf, nieuwste eerst.
gcloud firestore indexes composite create --collection-group=calls --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=caller_id \
  --field-config=order=DESCENDING,field-path=started_at \
  2>/dev/null || echo "index calls(caller_id, started_at) bestaat al"
gcloud firestore indexes composite create --collection-group=calls --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=company_id \
  --field-config=order=DESCENDING,field-path=started_at \
  2>/dev/null || echo "index calls(company_id, started_at) bestaat al"

step "Firebase koppelen (dashboard leest realtime)"
if firebase projects:addfirebase "$GCP_PROJECT" 2>/dev/null; then
  echo "Firebase toegevoegd"
else
  echo "Firebase was al gekoppeld, of je mist de rechten: controleer in console.firebase.google.com"
fi
if ! firebase apps:list WEB --project "$GCP_PROJECT" 2>/dev/null | grep -q callsight-dashboard; then
  firebase apps:create WEB callsight-dashboard --project "$GCP_PROJECT"
fi
echo "Firebase web-config voor frontend/.env (VITE_FIREBASE_*):"
firebase apps:sdkconfig WEB --project "$GCP_PROJECT" 2>/dev/null | grep -E 'apiKey|authDomain|projectId|appId' || true

step "Firestore security rules"
firebase deploy --only firestore:rules --project "$GCP_PROJECT" --config "$ROOT/firebase.json"

step "Anonieme Firebase Auth aanzetten"
TOKEN="$(gcloud auth print-access-token)"
curl -sf -X PATCH \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "X-Goog-User-Project: $GCP_PROJECT" \
  "https://identitytoolkit.googleapis.com/admin/v2/projects/${GCP_PROJECT}/config?updateMask=signIn.anonymous.enabled" \
  -d '{"signIn":{"anonymous":{"enabled":true}}}' >/dev/null \
  && echo "anonieme login aan" \
  || echo "lukte niet via API: zet 'Anonymous' aan in Firebase console > Authentication > Sign-in method"

step "Klaar"
cat <<EOF
Volgende stappen:
  1. cp .env.example .env  en vul GCP_PROJECT=$GCP_PROJECT
  2. Lokaal authenticeren gebeurt met ADC (gcloud auth application-default login), geen sa-key.json.
  3. Status indexen: gcloud firestore indexes composite list
  4. Cloud Run (rol B): --service-account=$SA --region=$REGION
EOF
