#!/usr/bin/env bash
# Firebase voor het dashboard (rol D): project koppelen, web-app registreren, Firestore rules uitrollen.
# Draai dit ná infra/gcp_setup.sh (rol B). Idempotent: veilig om opnieuw te draaien.
#
#   gcloud auth login && firebase login
#   GCP_PROJECT=<project-id> ./infra/firebase_setup.sh
#
# Schrijft niets naar de repo. De web-config (VITE_FIREBASE_*) wordt getoond; C zet die in frontend/.env.local.
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME=callsight-dashboard

say() { printf '\n==> %s\n' "$*"; }
command -v firebase >/dev/null || { echo "firebase CLI ontbreekt: npm install -g firebase-tools"; exit 1; }

say "API's"
gcloud services enable firebase.googleapis.com identitytoolkit.googleapis.com firebaserules.googleapis.com \
  firebasehosting.googleapis.com --project "$GCP_PROJECT"

say "Firebase koppelen aan $GCP_PROJECT"
if firebase projects:list 2>/dev/null | grep -q "$GCP_PROJECT"; then
  echo "   al gekoppeld"
else
  firebase projects:addfirebase "$GCP_PROJECT"
fi

say "Web-app $APP_NAME"
if ! firebase apps:list WEB --project "$GCP_PROJECT" 2>/dev/null | grep -q "$APP_NAME"; then
  firebase apps:create WEB "$APP_NAME" --project "$GCP_PROJECT"
fi
APP_ID="$(firebase apps:list WEB --project "$GCP_PROJECT" | grep "$APP_NAME" | grep -oE '1:[0-9]+:web:[a-z0-9]+' | head -1)"
CONFIG="$(firebase apps:sdkconfig WEB "$APP_ID" --project "$GCP_PROJECT")"
echo "   Voor frontend/.env.local (niet committen; staat in .gitignore):"
for pair in apiKey:API_KEY authDomain:AUTH_DOMAIN projectId:PROJECT_ID appId:APP_ID; do
  key="${pair%%:*}"; var="${pair##*:}"
  value="$(printf '%s' "$CONFIG" | grep -oE "\"?${key}\"?: *\"[^\"]+\"" | head -1 | sed -E 's/.*: *"([^"]+)"/\1/')"
  echo "   VITE_FIREBASE_${var}=${value}"
done

say "Firestore security rules (infra/firestore.rules)"
firebase deploy --only firestore:rules --project "$GCP_PROJECT" --config "$ROOT/firebase.json"

say "Anonieme login aanzetten (het dashboard logt anoniem in)"
TOKEN="$(gcloud auth print-access-token)"
if curl -sf -X PATCH \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "X-Goog-User-Project: $GCP_PROJECT" \
     "https://identitytoolkit.googleapis.com/admin/v2/projects/${GCP_PROJECT}/config?updateMask=signIn.anonymous.enabled" \
     -d '{"signIn":{"anonymous":{"enabled":true}}}' >/dev/null; then
  echo "   anonieme login staat aan"
else
  echo "   lukte niet via de API: zet 'Anonymous' aan op"
  echo "   https://console.firebase.google.com/project/${GCP_PROJECT}/authentication/providers"
fi

say "Klaar"
cat <<EOF
Nog te doen:
  1. De VITE_FIREBASE_*-regels hierboven in frontend/.env.local zetten (C), met VITE_FIREBASE_ANON_AUTH=true.
  2. Dashboard publiceren (na C's build):
       cd frontend && npm run build && cd .. && firebase deploy --only hosting --project ${GCP_PROJECT} --config firebase.json
     en https://${GCP_PROJECT}.web.app in de trigger-substitutie _FRONTEND_ORIGIN van de backend zetten (docs/backend.md).
EOF
