#!/bin/bash
# setup.sh — claudefree setup
#
# Detects if shell env is already configured. If so, skips to provider selection.
# Run with: bash setup.sh   or   source setup.sh

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"
ENV_FILE="$SCRIPT_DIR/.env"

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  claudefree Setup${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}\n"

SHELL_CONFIG=""
if [[ "$SHELL" == *"zsh"* ]]; then SHELL_CONFIG="$HOME/.zshrc"
elif [[ "$SHELL" == *"bash"* ]]; then SHELL_CONFIG="$HOME/.bashrc"; fi

ALREADY_CONFIGURED=0
if grep -q "ANTHROPIC_AUTH_TOKEN.*God" "$SHELL_CONFIG" 2>/dev/null; then
    ALREADY_CONFIGURED=1
fi

if [ "$ALREADY_CONFIGURED" == "1" ]; then
    echo -e "${GREEN}[OK] Shell env already configured, skipping!${NC}\n"
else
    echo -e "${YELLOW}[INFO] Shell env not configured — will set up at the end.${NC}\n"
fi

# ── 1. Install fzy ────────────────────────────────────────────────────────────

echo -e "${BLUE}[1/4] Checking fzy...${NC}"
if ! command -v fzy &> /dev/null; then
    echo -e "${YELLOW}Installing fzy...${NC}"
    case "$(uname -s)" in
        Linux*)
            if grep -qi 'fedora' /etc/os-release 2>/dev/null; then sudo dnf install -y fzy 2>/dev/null
            elif grep -qi 'debian\|ubuntu' /etc/os-release 2>/dev/null; then sudo apt-get update && sudo apt-get install -y fzy 2>/dev/null
            elif grep -qi 'arch' /etc/os-release 2>/dev/null; then sudo pacman -S fzy --noconfirm 2>/dev/null; fi
            ;;
        Darwin*) brew install fzy 2>/dev/null ;;
    esac
    if ! command -v fzy &> /dev/null; then
        TMP=$(mktemp -d); cd "$TMP"
        git clone https://github.com/jhawthorn/fzy.git && cd fzy && make && sudo make install
        cd - >/dev/null; rm -rf "$TMP"
    fi
fi
echo -e "${GREEN}[OK]${NC}\n"

# ── 2. Install jq ─────────────────────────────────────────────────────────────

echo -e "${BLUE}[2/5] Checking jq...${NC}"
if ! command -v jq &> /dev/null; then
    echo -e "${YELLOW}Installing jq...${NC}"
    case "$(uname -s)" in
        Linux*)
            if grep -qi 'fedora' /etc/os-release 2>/dev/null; then sudo dnf install -y jq 2>/dev/null
            elif grep -qi 'debian\|ubuntu' /etc/os-release 2>/dev/null; then sudo apt-get update && sudo apt-get install -y jq 2>/dev/null
            elif grep -qi 'arch' /etc/os-release 2>/dev/null; then sudo pacman -S jq --noconfirm 2>/dev/null; fi
            ;;
        Darwin*) brew install jq 2>/dev/null ;;
    esac
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}[FAIL] Could not install jq${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}[OK]${NC}\n"

# ── 3. Fetch providers ────────────────────────────────────────────────────────

echo -e "${BLUE}[3/5] Fetching providers from models.dev...${NC}"
TEMP_API=$(mktemp)
curl -s https://models.dev/api.json > "$TEMP_API" || { echo -e "${RED}[FAIL]${NC}"; exit 1; }
echo -e "${GREEN}[OK]${NC}\n"

# ── 3. Select provider + models + API key ─────────────────────────────────────

PROVIDERS=$(jq -r 'keys[]' "$TEMP_API" | sort)

echo -e "${BLUE}Select provider:${NC}"
if command -v fzy &>/dev/null && [ -t 0 ]; then
    SELECTED_PROVIDER=$(echo "$PROVIDERS" | fzy --prompt "Search provider: ")
else
    PROVIDER_ARRAY=($PROVIDERS)
    for i in "${!PROVIDER_ARRAY[@]}"; do echo "$((i+1)). ${PROVIDER_ARRAY[$i]}"; done
    echo -n "Enter number: "; read -r n
    SELECTED_PROVIDER="${PROVIDER_ARRAY[$((n-1))]}"
fi
[ -z "$SELECTED_PROVIDER" ] && { echo -e "${RED}[FAIL]${NC}"; exit 1; }
echo -e "${GREEN}[OK] $SELECTED_PROVIDER${NC}\n"

# API key
PROVIDER_UPPER=$(echo "$SELECTED_PROVIDER" | tr '[:lower:]' '[:upper:]')
API_KEY_VAR="${PROVIDER_UPPER}_API_KEY"
API_KEY=""
if [ -f "$ENV_FILE" ] && grep -q "^${API_KEY_VAR}=" "$ENV_FILE"; then
    API_KEY=$(grep "^${API_KEY_VAR}=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    echo -e "${GREEN}[OK] API key found${NC}"
else
    echo -n "Enter API key for $SELECTED_PROVIDER: "
    read -rs API_KEY; echo ""
    [ -z "$API_KEY" ] && { echo -e "${RED}[FAIL]${NC}"; exit 1; }
fi

# Models
echo -e "\n${BLUE}[4/5] Fetching models...${NC}"
MODELS=$(jq -r ".\"$SELECTED_PROVIDER\".models | keys[]" "$TEMP_API" | sort)
[ -z "$MODELS" ] && { echo -e "${RED}[FAIL]${NC}"; exit 1; }
MODEL_ARRAY=($MODELS)
MODEL_COUNT=${#MODEL_ARRAY[@]}
echo -e "${GREEN}[OK] $MODEL_COUNT models${NC}\n"

select_model() {
    local tier=$1
    echo -e "${BLUE}Model for $tier:${NC}" >&2
    echo "0. [SAME_AS_DEFAULT]" >&2; echo "1. [CUSTOM_MODEL]" >&2
    local count=0
    for i in "${!MODEL_ARRAY[@]}"; do [ "$count" -ge 10 ] && break; echo "$((i+2)). ${MODEL_ARRAY[$i]}" >&2; ((count++)); done
    [ "$MODEL_COUNT" -gt 10 ] && echo "... and $((MODEL_COUNT-10)) more" >&2
    if command -v fzy &>/dev/null && [ -t 0 ]; then
        choice=$(printf "[SAME_AS_DEFAULT]\n[CUSTOM_MODEL]\n%s\n" "$MODELS" | fzy --prompt "Search $tier: ")
    else
        echo -n "Number (0-$((MODEL_COUNT+1))): " >&2; read -r n
        case "$n" in 0) choice="[SAME_AS_DEFAULT]";; 1) choice="[CUSTOM_MODEL]";; *) [ "$n" -ge 2 ] && [ "$n" -lt $((MODEL_COUNT+2)) ] && choice="${MODEL_ARRAY[$((n-2))]}" || { echo -e "${RED}Invalid${NC}" >&2; select_model "$tier"; return; };; esac
    fi
    [ "$choice" = "[CUSTOM_MODEL]" ] && echo -n "Custom name: " >&2 && read -r choice
    echo "$choice"
}

MODEL_DEFAULT=$(select_model "DEFAULT")
MODEL_OPUS=$(select_model "OPUS")
MODEL_SONNET=$(select_model "SONNET")
MODEL_HAIKU=$(select_model "HAIKU")
echo -e "${GREEN}[OK]${NC}\n"

# ── 4. Save ───────────────────────────────────────────────────────────────────

echo -e "${BLUE}[5/5] Saving...${NC}"

cat > "$CONFIG_FILE" <<EOF
{
  "provider": "$SELECTED_PROVIDER",
  "model_default": "$MODEL_DEFAULT",
  "model_opus": "$MODEL_OPUS",
  "model_sonnet": "$MODEL_SONNET",
  "model_haiku": "$MODEL_HAIKU"
}
EOF

if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" <<EOF
# claudefree credentials
${PROVIDER_UPPER}_API_KEY="$API_KEY"
ANTHROPIC_AUTH_TOKEN="God"
EOF
else
    grep -q "^${PROVIDER_UPPER}_API_KEY=" "$ENV_FILE" || echo "${PROVIDER_UPPER}_API_KEY=\"$API_KEY\"" >> "$ENV_FILE"
    grep -q "^ANTHROPIC_AUTH_TOKEN=" "$ENV_FILE" || echo 'ANTHROPIC_AUTH_TOKEN="God"' >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

rm -f "$TEMP_API"

# ── Shell env vars (only if NOT already configured) ───────────────────────────

if [ "$ALREADY_CONFIGURED" == "0" ] && [ -n "$SHELL_CONFIG" ]; then
    echo ""
    echo -e "${BLUE}Setting up ANTHROPIC env vars in $SHELL_CONFIG...${NC}"
    [ -f "$SHELL_CONFIG" ] && cp "$SHELL_CONFIG" "$SHELL_CONFIG.backup"
    cat >> "$SHELL_CONFIG" << 'EOF'

# claudefree Configuration
export ANTHROPIC_AUTH_TOKEN="God"
export ANTHROPIC_BASE_URL="http://localhost:16324"
EOF
    echo -e "${GREEN}[OK] Added to $SHELL_CONFIG${NC}"
    echo -e "${YELLOW}Run: source $SHELL_CONFIG   (or restart terminal)${NC}"

    if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
        export ANTHROPIC_AUTH_TOKEN="God"
        export ANTHROPIC_BASE_URL="http://localhost:16324"
        echo -e "${GREEN}[OK] Exported to current shell${NC}"
    fi
else
    echo -e "${GREEN}[OK] Shell env already configured, skipping${NC}"
fi

# ── Install claude-start-server to PATH ────────────────────────────────────────

echo ""
echo -e "${BLUE}Installing claude-start-server to PATH...${NC}"
mkdir -p "$HOME/.local/bin"
if [ -f "$SCRIPT_DIR/claude-start-server" ]; then
    ln -sf "$SCRIPT_DIR/claude-start-server" "$HOME/.local/bin/claude-start-server" 2>/dev/null || cp "$SCRIPT_DIR/claude-start-server" "$HOME/.local/bin/claude-start-server"
    echo -e "${GREEN}[OK] ~/.local/bin/claude-start-server${NC}"
fi

# ── Install claude-code CLI (if missing) ─────────────────────────

echo ""
echo -e "${BLUE}Checking claude CLI...${NC}"
if command -v claude &> /dev/null; then
    echo -e "${GREEN}[OK] claude found${NC}"
else
    echo -e "${YELLOW}claude not found — installing via npm...${NC}"
    if command -v npm &> /dev/null; then
        npm install -g @anthropic-ai/claude-code
        if command -v claude &> /dev/null; then
            echo -e "${GREEN}[OK] claude installed${NC}"
        else
            echo -e "${RED}[FAIL] npm install failed${NC}"
        fi
    else
        echo -e "${RED}[FAIL] npm not found. Install Node.js first: https://nodejs.org${NC}"
    fi
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}[OK] Setup Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}\n"

echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. Start proxy:  ${YELLOW}claude-start-server${NC}"
echo -e "  2. Run claude:    ${YELLOW}claude${NC}"
echo -e ""
echo -e "  Config:  ${BLUE}$CONFIG_FILE${NC}"
echo -e "  Secrets: ${BLUE}$ENV_FILE${NC}\n"
