#!/usr/bin/env bash
# =============================================================================
# PostMule developer one-time GCP setup
#
# Run this ONCE as the PostMule developer/owner to:
#   1. Create the PostMule GCP project
#   2. Enable Gmail, Drive, Sheets, and Gemini APIs
#   3. Guide you through OAuth consent screen + client creation
#   4. Update postmule/core/constants.py with the baked-in client credentials
#
# Prerequisites:
#   gcloud auth login      (run first — opens a browser to authenticate)
#
# Usage:
#   bash scripts/dev_setup.sh
# =============================================================================

set -euo pipefail

GCLOUD="${GCLOUD:-gcloud}"
PROJECT_ID="postmule-app"
PROJECT_NAME="PostMule"
CONSTANTS_FILE="postmule/core/constants.py"

# Colours
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
CYN='\033[0;36m'
NC='\033[0m'

step()  { echo -e "\n${CYN}==> $*${NC}"; }
ok()    { echo -e "    ${GRN}OK:${NC} $*"; }
warn()  { echo -e "    ${YLW}NOTE:${NC} $*"; }
fail()  { echo -e "    ${RED}FAIL:${NC} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Verify gcloud is authenticated
# ---------------------------------------------------------------------------
step "Verifying gcloud authentication..."
if ! "$GCLOUD" auth list --filter="status:ACTIVE" --format="value(account)" 2>/dev/null | grep -q "@"; then
    fail "Not authenticated. Run:  gcloud auth login"
fi
ACTIVE_ACCOUNT=$("$GCLOUD" auth list --filter="status:ACTIVE" --format="value(account)" 2>/dev/null | head -1)
ok "Authenticated as: $ACTIVE_ACCOUNT"

# ---------------------------------------------------------------------------
# 1. Create GCP project (skip if already exists)
# ---------------------------------------------------------------------------
step "Creating GCP project: $PROJECT_ID..."
if "$GCLOUD" projects describe "$PROJECT_ID" &>/dev/null; then
    warn "Project $PROJECT_ID already exists — skipping creation."
else
    "$GCLOUD" projects create "$PROJECT_ID" --name="$PROJECT_NAME"
    ok "Project $PROJECT_ID created."
fi

"$GCLOUD" config set project "$PROJECT_ID" --quiet
ok "Active project set to $PROJECT_ID."

# ---------------------------------------------------------------------------
# 2. Enable required APIs
# ---------------------------------------------------------------------------
step "Enabling APIs (Gmail, Drive, Sheets, Generative Language)..."
APIS=(
    "gmail.googleapis.com"
    "drive.googleapis.com"
    "sheets.googleapis.com"
    "generativelanguage.googleapis.com"
)
for api in "${APIS[@]}"; do
    echo "    Enabling $api..."
    "$GCLOUD" services enable "$api" --quiet
done
ok "All APIs enabled."

# ---------------------------------------------------------------------------
# 3. OAuth consent screen + client — manual Console steps
# ---------------------------------------------------------------------------
step "OAuth consent screen configuration (manual — 4 steps in Cloud Console)"
echo ""
echo -e "  ${YLW}You need to complete these steps in Google Cloud Console.${NC}"
echo -e "  They take about 3 minutes."
echo ""
echo "  Step A — Configure the OAuth consent screen:"
echo "  Open this URL in your browser:"
echo -e "  ${CYN}https://console.cloud.google.com/apis/credentials/consent?project=$PROJECT_ID${NC}"
echo ""
echo "  Fill in:"
echo "    User Type:        External"
echo "    App name:         PostMule"
echo "    User support email: $ACTIVE_ACCOUNT"
echo "    Developer email:  $ACTIVE_ACCOUNT"
echo "    Scopes (click Add or Remove Scopes):"
echo "      .../auth/gmail.readonly"
echo "      .../auth/gmail.modify"
echo "      .../auth/drive"
echo "      .../auth/spreadsheets"
echo "    Test users: add $ACTIVE_ACCOUNT and any test Gmail addresses"
echo ""
echo "  Step B — Create a Desktop OAuth client:"
echo "  Open this URL:"
echo -e "  ${CYN}https://console.cloud.google.com/apis/credentials/oauthclient?project=$PROJECT_ID${NC}"
echo ""
echo "    Application type: Desktop app"
echo "    Name:             PostMule Desktop"
echo "    Click Create"
echo ""
echo "  Step C — Copy the Client ID and Client Secret shown in the popup."
echo ""
read -p "  Press Enter once you have both values ready..." _

# ---------------------------------------------------------------------------
# 4. Collect client credentials
# ---------------------------------------------------------------------------
step "Enter the OAuth client credentials you just copied..."
read -p "    Client ID:     " CLIENT_ID
read -s -p "    Client Secret: " CLIENT_SECRET
echo ""

if [[ -z "$CLIENT_ID" || -z "$CLIENT_SECRET" ]]; then
    fail "Client ID or Client Secret cannot be empty."
fi

ok "Credentials received."

# ---------------------------------------------------------------------------
# 5. Inject into postmule/core/constants.py
# ---------------------------------------------------------------------------
step "Updating $CONSTANTS_FILE with baked-in client credentials..."

if [[ ! -f "$CONSTANTS_FILE" ]]; then
    fail "$CONSTANTS_FILE not found. Run from project root."
fi

# Replace the placeholder lines
python3 - <<PYEOF
import re, pathlib

path = pathlib.Path("$CONSTANTS_FILE")
text = path.read_text(encoding="utf-8")

text = re.sub(
    r'^GOOGLE_CLIENT_ID\s*=.*$',
    'GOOGLE_CLIENT_ID: str = "$CLIENT_ID"',
    text, flags=re.MULTILINE
)
text = re.sub(
    r'^GOOGLE_CLIENT_SECRET\s*=.*$',
    'GOOGLE_CLIENT_SECRET: str = "$CLIENT_SECRET"',
    text, flags=re.MULTILINE
)

path.write_text(text, encoding="utf-8")
print("  Updated $CONSTANTS_FILE")
PYEOF

ok "constants.py updated."

# ---------------------------------------------------------------------------
# 6. Run google_auth.py to obtain the developer's refresh token
# ---------------------------------------------------------------------------
step "Running OAuth flow to obtain your personal refresh token..."
echo "    This will open a browser. Sign in with: $ACTIVE_ACCOUNT"
echo "    Grant all requested permissions."
echo ""

# Determine Python in venv or fallback
PYTHON=".venv/Scripts/python"
[[ -f "$PYTHON" ]] || PYTHON="python3"

"$PYTHON" scripts/google_auth.py --output credentials.yaml
ok "credentials.yaml written."

# ---------------------------------------------------------------------------
# 7. Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${GRN}$(printf '=%.0s' {1..60})${NC}"
echo -e "${GRN}  Developer setup complete!${NC}"
echo -e "${GRN}$(printf '=%.0s' {1..60})${NC}"
echo ""
echo "  Client ID and Secret are now baked into $CONSTANTS_FILE."
echo "  Your personal refresh token is in credentials.yaml."
echo ""
echo "  Next steps:"
echo "    1. Commit $CONSTANTS_FILE  (client_id/secret are safe to commit for Desktop apps)"
echo "    2. Run unit tests:   .venv/Scripts/pytest tests/unit/ -v"
echo "    3. Run dry-run:      .venv/Scripts/postmule --dry-run"
echo ""
echo -e "  ${YLW}IMPORTANT: Do NOT commit credentials.yaml (refresh token)${NC}"
echo "  It is already in .gitignore."
echo ""
