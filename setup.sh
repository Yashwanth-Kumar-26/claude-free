#!/bin/bash
# setup.sh — claudefree Setup (preferred)
#
# Run with: bash setup.sh   or   source setup.sh
# Bootstraps the project on Linux/macOS: creates virtualenv, installs deps, writes config.json and .env
# Detects if shell env is already configured and guides provider selection.

set -euo pipefail

# ── Cleanup on exit / interrupt ─────────────────────────────────────────
TEMP_FILES=()
cleanup() {
    rm -f "${TEMP_FILES[@]}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── ANSI Colors (use echo -e, not printf, for these) ────────────────────
RST='\033[0m'; BLD='\033[1m'; DIM='\033[2m'
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'

# ── Terminal helpers ──────────────────────────────────────────────────────
COLS=$(tput cols 2>/dev/null || echo 80)
[ "$COLS" -gt 80 ] && COLS=80

# Portable repeat-char (no dependency on seq)
repeat() { printf '%*s' "$1" '' | tr ' ' "$2"; }

# Print helpers — use echo -e so \033 escape sequences work everywhere
print_banner() {
    local line
    echo -e "${CYAN}"
    line=$(repeat $((COLS-2)) '═')
    printf '╔%s╗\n' "$line"
    printf '║%*s║\n' $((COLS-2)) ""
    printf "║%*s✦ claudefree Setup ✦%*s║\n" \
        $(( (COLS-4)/2 - 9 )) "" $(( (COLS-4) - (COLS-4)/2 - 9 )) ""
    printf '║%*sFree AI for Claude Code — Multi-Provider%*s║\n' \
        $(( (COLS-4)/2 - 19 )) "" $(( (COLS-4) - (COLS-4)/2 - 19 )) ""
    printf '║%*s║\n' $((COLS-1)) ""
    printf '╚%s╝\n' "$line"
    echo -e "${RST}"
}

print_step() {
    local num=$1 total=$2 desc=$3
    echo -e "\n  ${BLUE}◉${RST} ${BLD}Step $num of $total${RST}  $desc"
}

print_ok()    { echo -e "  ${GREEN}✓${RST} $1"; }
print_info()  { echo -e "  ${CYAN}ℹ${RST} $1"; }
print_warn()  { echo -e "  ${YELLOW}⚠${RST} $1"; }
print_err()   { echo -e "  ${RED}✗${RST} $1"; }
print_sub()   { echo -e "    ${CYAN}⏳${RST} $1"; }
print_sub_ok(){ echo -e "    ${GREEN}✓${RST} $1"; }
print_sub_ko(){ echo -e "    ${RED}✗${RST} $1"; }
print_divider(){ echo -e "  ${DIM}────────────────────────────────────${RST}"; }

# ── Spinner for long operations ──────────────────────────────────────────
# Usage: run_with_spinner "message" command [args...]
# Returns the exit code of command.
run_with_spinner() {
    local msg=$1
    shift
    local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0

    # Run in background, collecting exit code
    "$@" > /dev/null 2>&1 &
    local pid=$!

    while kill -0 "$pid" 2>/dev/null; do
        printf "\r    ${CYAN}%s${RST} %s" "${spin:$i:1}" "$msg"
        i=$(( (i+1) % ${#spin} ))
        sleep 0.1
    done
    wait "$pid"
    local rc=$?
    if [ $rc -eq 0 ]; then
        printf "\r    ${GREEN}✓${RST} %s${DIM}   ${RST}\n" "$msg"
    else
        printf "\r    ${RED}✗${RST} %s${DIM}   ${RST}\n" "$msg"
    fi
    return $rc
}

# ── Summary Dashboard ─────────────────────────────────────────────────────
show_summary() {
    local provider=$1 mdef=$2 mopus=$3 mson=$4 mhai=$5 cf=$6 ef=$7
    local w=$((COLS-4))
    local line
    line=$(repeat $((COLS-2)) '═')

    echo -e "\n${GREEN}"
    printf '╔%s╗\n' "$line"
    printf "║%*s${RST}${BLD}${GREEN}  ✓ Setup Complete${RST}${GREEN}%*s║\n" \
        $(( (COLS-4)/2 - 7 )) "" $(( (COLS-4) - (COLS-4)/2 - 7 )) ""
    printf '╠%s╣\n' "$line"
    printf "║  ${BLD}%-20s${RST}${GREEN} %-${w}s${RST}${GREEN}║\n" "Provider" "$provider"
    printf "║  ${BLD}%-20s${RST}${GREEN} %-${w}s${RST}${GREEN}║\n" "Default Model" "$mdef"
    printf "║  ${BLD}%-20s${RST}${GREEN} %-${w}s${RST}${GREEN}║\n" "Opus Model" "$mopus"
    printf "║  ${BLD}%-20s${RST}${GREEN} %-${w}s${RST}${GREEN}║\n" "Sonnet Model" "$mson"
    printf "║  ${BLD}%-20s${RST}${GREEN} %-${w}s${RST}${GREEN}║\n" "Haiku Model" "$mhai"
    printf '╠%s╣\n' "$line"
    printf "║  ${DIM}%-20s${RST}${GREEN} %-${w}s${RST}${GREEN}║\n" "Config" "$cf"
    printf "║  ${DIM}%-20s${RST}${GREEN} %-${w}s${RST}${GREEN}║\n" "Secrets" "$ef"
    printf '╠%s╣\n' "$line"
    echo -e "${GREEN}║  ${RST}${BLD}Next Steps:${RST}${GREEN}                                    ║${RST}"
    echo -e "${GREEN}║  ${RST}${CYAN}  1.${RST} Start proxy → ${BLD}claude-start-server${RST}${GREEN}            ║${RST}"
    echo -e "${GREEN}║  ${RST}${CYAN}  2.${RST} Run Claude  → ${BLD}claude${RST}${GREEN}                         ║${RST}"
    printf '╚%s╝\n' "$line"
    echo -e "${RST}"
}

# ── OS detection ──────────────────────────────────────────────────────────
pkg_install() {
    local pkg=$1
    case "$(uname -s)" in
        Linux*)
            if   grep -qi 'fedora' /etc/os-release 2>/dev/null; then sudo dnf install -y "$pkg" > /dev/null 2>&1
            elif grep -qi 'debian\|ubuntu' /etc/os-release 2>/dev/null; then sudo apt-get install -y -qq "$pkg" > /dev/null 2>&1
            elif grep -qi 'arch' /etc/os-release 2>/dev/null; then sudo pacman -S "$pkg" --noconfirm > /dev/null 2>&1
            else return 1; fi
            ;;
        Darwin*) brew install "$pkg" > /dev/null 2>&1 ;;
        *) return 1 ;;
    esac
}

# ── Main ──────────────────────────────────────────────────────────────────
main() {
    print_banner

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CONFIG_FILE="$SCRIPT_DIR/config.json"
    ENV_FILE="$SCRIPT_DIR/.env"

    # ── Shell config detection ────────────────────────────────────────────
    SHELL_CONFIG=""
    if [[ "$SHELL" == *"zsh"* ]]; then SHELL_CONFIG="$HOME/.zshrc"
    elif [[ "$SHELL" == *"bash"* ]]; then SHELL_CONFIG="$HOME/.bashrc"; fi

    ALREADY_CONFIGURED=0
    if [ -n "$SHELL_CONFIG" ] && grep -q "ANTHROPIC_AUTH_TOKEN.*God" "$SHELL_CONFIG" 2>/dev/null; then
        ALREADY_CONFIGURED=1
        print_ok "Shell env already configured — skipping environment setup"
    else
        print_info "Fresh setup — will configure everything"
    fi

    TOTAL_STEPS=8

    # ══════════════════════════════════════════════════════════════════════
    # Step 1: Install uv (package manager)
    # ══════════════════════════════════════════════════════════════════════
    print_step 1 $TOTAL_STEPS "Checking uv (package manager)"

    if ! command -v uv &> /dev/null; then
        print_sub "Installing uv..."
        if command -v curl &> /dev/null; then
            curl -LsSf https://astral.sh/uv/install.sh | sh > /dev/null 2>&1 || true
        fi
        # Refresh PATH
    # shellcheck disable=SC1091
    if [ -f "$HOME/.cargo/env" ]; then
        . "$HOME/.cargo/env"
    fi
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi

    if command -v uv &> /dev/null; then
        print_sub_ok "uv $(uv --version 2>/dev/null || echo 'ready')"
    else
        print_warn "uv not found — install manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi

    # ══════════════════════════════════════════════════════════════════════
    # Step 2: Install fzf (fuzzy finder)
    # ══════════════════════════════════════════════════════════════════════
    print_step 2 $TOTAL_STEPS "Checking fuzzy finder (fzf)"

    if ! command -v fzf &> /dev/null; then
        print_sub "Installing fzf via package manager..."
        pkg_install fzf || true
    fi

    if ! command -v fzf &> /dev/null; then
        print_warn "Package install failed — trying git clone..."
        TMP=$(mktemp -d)
        (
            cd "$TMP"
            git clone --depth 1 https://github.com/junegunn/fzf.git --quiet 2>/dev/null
            cd fzf && ./install --bin 2>/dev/null
        ) > /dev/null 2>&1 || true
        rm -rf "$TMP"
        # fzf installs to ~/.fzf/bin
        if [ -f "$HOME/.fzf/bin/fzf" ]; then
            mkdir -p "$HOME/.local/bin"
            ln -sf "$HOME/.fzf/bin/fzf" "$HOME/.local/bin/fzf" 2>/dev/null || true
            export PATH="$HOME/.local/bin:$PATH"
        fi
    fi

    if command -v fzf &> /dev/null; then
        print_sub_ok "fzf ready"
    else
        print_warn "fzf not available — using numbered menu"
    fi

    # ══════════════════════════════════════════════════════════════════════
    # Step 3: Install jq (JSON parser)
    # ══════════════════════════════════════════════════════════════════════
    print_step 3 $TOTAL_STEPS "Checking jq (JSON parser)"

    if ! command -v jq &> /dev/null; then
        print_sub "Installing jq..."
        if ! pkg_install jq; then
            print_sub_ko "Could not install jq via package manager"
            print_warn "Install jq manually:"
            echo -e "      ${BLD}brew install jq${RST}        (macOS)"
            echo -e "      ${BLD}sudo apt install jq${RST}   (Debian/Ubuntu)"
            echo -e "      ${BLD}sudo dnf install jq${RST}   (Fedora)"
            exit 1
        fi
    fi

    if command -v jq &> /dev/null; then
        print_sub_ok "jq ready"
    else
        print_err "jq not found after install attempt"
        exit 1
    fi

    # ══════════════════════════════════════════════════════════════════════
    # Step 4: Fetch providers
    # ══════════════════════════════════════════════════════════════════════
    print_step 4 $TOTAL_STEPS "Fetching providers from models.dev"
    TEMP_API=$(mktemp)
    TEMP_FILES+=("$TEMP_API")

    if run_with_spinner "Downloading provider list..." curl -s --max-time 30 "https://models.dev/api.json" -o "$TEMP_API"; then
        print_sub_ok "Provider list downloaded (${DIM}$(wc -c < "$TEMP_API") bytes${RST})"
    else
        print_err "Failed to fetch providers — check your internet connection"
        rm -f "$TEMP_API"
        exit 1
    fi

    # ══════════════════════════════════════════════════════════════════════
    # Step 5: Install deps with uv
    # ══════════════════════════════════════════════════════════════════════
    print_step 5 $TOTAL_STEPS "Installing project dependencies"

    if command -v uv &> /dev/null; then
        if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
            if run_with_spinner "Running uv sync..." uv sync --directory "$SCRIPT_DIR"; then
                print_sub_ok "Dependencies installed via uv"
            else
                print_warn "uv sync failed — falling back to pip install -e ."
                if pip install -e "$SCRIPT_DIR" > /dev/null 2>&1; then
                    print_sub_ok "pip install succeeded"
                else
                    print_warn "pip install failed"
                fi
            fi
        else
            print_warn "No pyproject.toml found — skipping uv sync"
        fi
    else
        print_sub "uv not available — using pip..."
        if pip install -e "$SCRIPT_DIR" > /dev/null 2>&1; then
            print_sub_ok "pip install succeeded"
        else
            print_warn "pip install failed"
        fi
    fi

    # ══════════════════════════════════════════════════════════════════════
    # Step 6: Select provider + API key
    # ══════════════════════════════════════════════════════════════════════
    print_step 6 $TOTAL_STEPS "Select provider and enter API key"

    PROVIDERS=$(jq -r 'keys[]' "$TEMP_API" | sort)

    echo ""
    if command -v fzf &>/dev/null && [ -t 0 ]; then
        echo -e "    ${DIM}(Type to filter, press Enter to select)${RST}"
        SELECTED_PROVIDER=$(echo "$PROVIDERS" | fzf --prompt "  Provider > ")
    else
        local IFS=$'\n'
        read -r -d '' -a PROVIDER_LIST <<< "$PROVIDERS" 2>/dev/null || true
        unset IFS
        echo ""
        for i in "${!PROVIDER_LIST[@]}"; do
            printf "    ${CYAN}%3d${RST}) %s\n" "$((i+1))" "${PROVIDER_LIST[$i]}"
        done
        echo ""
        printf '    %sEnter number%s (1-%s): ' "${BLD}" "${RST}" "${#PROVIDER_LIST[@]}"
        read -r n
        SELECTED_PROVIDER="${PROVIDER_LIST[$((n-1))]}"
    fi

    if [ -z "$SELECTED_PROVIDER" ]; then
        print_err "No provider selected"
        rm -f "$TEMP_API"
        exit 1
    fi
    print_sub_ok "Selected: ${BLD}$SELECTED_PROVIDER${RST}"

    # ── API key ───────────────────────────────────────────────────────────
    PROVIDER_UPPER=$(echo "$SELECTED_PROVIDER" | tr '[:lower:]' '[:upper:]')
    API_KEY_VAR="${PROVIDER_UPPER}_API_KEY"
    API_KEY=""

    if [ -f "$ENV_FILE" ] && grep -q "^${API_KEY_VAR}=" "$ENV_FILE"; then
        API_KEY=$(grep "^${API_KEY_VAR}=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
        print_sub_ok "API key found in .env"
    else
        echo ""
        echo -e "    ${BLD}Enter your API key for ${CYAN}$SELECTED_PROVIDER${RST}:"
        printf '    %s(input hidden)%s ' "${DIM}" "${RST}"
        read -rs API_KEY
        echo ""
        if [ -z "$API_KEY" ]; then
            print_err "API key cannot be empty"
            rm -f "$TEMP_API"
            exit 1
        fi
        print_sub_ok "API key received"
    fi

    # ══════════════════════════════════════════════════════════════════════
    # Step 7: Select models for each tier
    # ══════════════════════════════════════════════════════════════════════
    echo ""
    print_step 7 $TOTAL_STEPS "Select models per tier"

    MODELS=$(jq -r ".\"$SELECTED_PROVIDER\".models | keys[]" "$TEMP_API" | sort)
    if [ -z "$MODELS" ]; then
        print_err "No models found for provider '$SELECTED_PROVIDER'"
        rm -f "$TEMP_API"
        exit 1
    fi

    IFS=$'\n' read -r -d '' -a MODEL_ARRAY <<< "$MODELS" 2>/dev/null || true
    MODEL_COUNT=${#MODEL_ARRAY[@]}
    print_info "$MODEL_COUNT models available"

    select_model() {
        local tier=$1
        # All display output goes to stderr — only the final choice goes to stdout
        echo >&2 ""
        echo >&2 -e "    ${BLUE}── Model for ${BLD}$tier${RST}${BLUE} ──${RST}"
        echo >&2 -e "      ${DIM} 0${RST}) [SAME_AS_DEFAULT]"
        echo >&2 -e "      ${DIM} 1${RST}) [CUSTOM_MODEL]"

        local shown=0
        for i in "${!MODEL_ARRAY[@]}"; do
            [ "$shown" -ge 10 ] && break
            echo >&2 -e "      ${DIM}$((i+2))${RST}) ${MODEL_ARRAY[$i]}"
            ((shown++))
        done
        [ "$MODEL_COUNT" -gt 10 ] && echo >&2 -e "      ${DIM}... and $((MODEL_COUNT-10)) more${RST}"

        local choice="[SAME_AS_DEFAULT]"
        if command -v fzf &>/dev/null && [ -t 0 ]; then
            echo >&2 -e "      ${DIM}(Type to filter, Enter to select)${RST}"
            choice=$(printf "[SAME_AS_DEFAULT]\n[CUSTOM_MODEL]\n%s\n" "$MODELS" | fzf --prompt "  Search $tier > ")
        else
            echo >&2 ""
            printf '      %sSelection%s (0-%s): ' "${BLD}" "${RST}" "$((MODEL_COUNT+1))" >&2
            read -r n
            case "$n" in
                0) choice="[SAME_AS_DEFAULT]" ;;
                1) printf '      %sCustom name%s: ' "${BLD}" "${RST}" >&2; read -r choice ;;
                *)
                    if [ "$n" -ge 2 ] && [ "$n" -lt $((MODEL_COUNT+2)) ]; then
                        choice="${MODEL_ARRAY[$((n-2))]}"
                    else
                        print_warn "Invalid — using [SAME_AS_DEFAULT]"
                        choice="[SAME_AS_DEFAULT]"
                    fi
                    ;;
            esac
        fi
        echo "$choice"
    }

    MODEL_DEFAULT=$(select_model "DEFAULT")
    MODEL_OPUS=$(   select_model "OPUS")
    MODEL_SONNET=$( select_model "SONNET")
    MODEL_HAIKU=$(  select_model "HAIKU")

    print_divider
    echo -e "    ${GREEN}DEFAULT${RST} → $MODEL_DEFAULT"
    echo -e "    ${MAGENTA}OPUS${RST}    → $MODEL_OPUS"
    echo -e "    ${YELLOW}SONNET${RST}   → $MODEL_SONNET"
    echo -e "    ${CYAN}HAIKU${RST}    → $MODEL_HAIKU"
    print_sub_ok "Models configured"

    # ══════════════════════════════════════════════════════════════════════
    # Step 8: Save configuration
    # ══════════════════════════════════════════════════════════════════════
    print_step 8 $TOTAL_STEPS "Saving configuration"

    # Write config.json
    cat > "$CONFIG_FILE" <<EOF
{
  "provider": "$SELECTED_PROVIDER",
  "model_default": "$MODEL_DEFAULT",
  "model_opus": "$MODEL_OPUS",
  "model_sonnet": "$MODEL_SONNET",
  "model_haiku": "$MODEL_HAIKU"
}
EOF
    print_sub_ok "config.json written"

    # Write .env
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" <<EOF
# claudefree credentials
${PROVIDER_UPPER}_API_KEY="$API_KEY"
ANTHROPIC_AUTH_TOKEN="God"
EOF
        print_sub_ok ".env created with secure permissions"
    else
        grep -q "^${PROVIDER_UPPER}_API_KEY=" "$ENV_FILE" || echo "${PROVIDER_UPPER}_API_KEY=\"$API_KEY\"" >> "$ENV_FILE"
        grep -q "^ANTHROPIC_AUTH_TOKEN=" "$ENV_FILE" || echo 'ANTHROPIC_AUTH_TOKEN="God"' >> "$ENV_FILE"
        print_sub_ok ".env updated"
    fi
    chmod 600 "$ENV_FILE"
    rm -f "$TEMP_API"

    print_info "Config:  ${DIM}$CONFIG_FILE${RST}"
    print_info "Secrets: ${DIM}$ENV_FILE${RST}"

    # ── Shell env vars ────────────────────────────────────────────────────
    if [ "$ALREADY_CONFIGURED" == "0" ] && [ -n "$SHELL_CONFIG" ] && [ -f "$SHELL_CONFIG" ]; then
        echo ""
        print_info "Adding ANTHROPIC vars to ${BLD}$SHELL_CONFIG${RST}"
        cp "$SHELL_CONFIG" "$SHELL_CONFIG.backup" 2>/dev/null || true
        cat >> "$SHELL_CONFIG" << 'EOF'

# claudefree Configuration
export ANTHROPIC_AUTH_TOKEN="God"
export ANTHROPIC_BASE_URL="http://localhost:16324"
EOF
        print_sub_ok "Added to $SHELL_CONFIG"
        print_info "Run: ${BLD}source $SHELL_CONFIG${RST}"

        if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
            export ANTHROPIC_AUTH_TOKEN="God"
            export ANTHROPIC_BASE_URL="http://localhost:16324"
            print_sub_ok "Exported to current shell"
        fi
    else
        print_info "Shell env already configured — skipped"
    fi

    # ── Install claude-start-server to PATH ───────────────────────────────
    echo ""
    print_info "Installing claude-start-server to PATH..."
    mkdir -p "$HOME/.local/bin"
    if [ -f "$SCRIPT_DIR/claude-start-server" ]; then
        ln -sf "$SCRIPT_DIR/claude-start-server" "$HOME/.local/bin/claude-start-server" 2>/dev/null || \
            cp "$SCRIPT_DIR/claude-start-server" "$HOME/.local/bin/claude-start-server"
        print_sub_ok "$HOME/.local/bin/claude-start-server"
    else
        print_warn "claude-start-server not found in project"
    fi

    # ── Check claude CLI ──────────────────────────────────────────────────
    echo ""
    print_info "Checking Claude Code CLI..."
    if command -v claude &> /dev/null; then
        claude_ver=$(claude --version 2>/dev/null || echo "installed")
        print_sub_ok "claude CLI found ($claude_ver)"
    else
        print_warn "claude not found — installing via npm..."
        if command -v npm &> /dev/null; then
            npm install -g @anthropic-ai/claude-code > /dev/null 2>&1
            if command -v claude &> /dev/null; then
                print_sub_ok "claude installed"
            else
                print_err "npm install failed"
            fi
        else
            print_err "npm not found — install Node.js: ${BLD}https://nodejs.org${RST}"
        fi
    fi

    # ── Final summary ─────────────────────────────────────────────────────
    show_summary "$SELECTED_PROVIDER" "$MODEL_DEFAULT" "$MODEL_OPUS" \
                 "$MODEL_SONNET" "$MODEL_HAIKU" "$CONFIG_FILE" "$ENV_FILE"
}

main
