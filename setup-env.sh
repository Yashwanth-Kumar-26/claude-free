#!/bin/bash
# setup-env.sh — Configure ANTHROPIC environment variables for Linux/macOS
#
# USAGE: source setup-env.sh   (run with source, NOT bash setup-env.sh!)

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "[WARN] This script must be sourced to apply env vars to your current shell."
    echo "       Run:  source setup-env.sh"
    echo "       Or:   . setup-env.sh"
    echo ""
    echo "       Writing config only — restart terminal or run 'source setup-env.sh' later."
    WRITE_ONLY=1
else
    WRITE_ONLY=0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHELL_CONFIG=""

# Detect shell
if [[ "$SHELL" == *"zsh"* ]]; then
    SHELL_CONFIG="$HOME/.zshrc"
    SHELL_NAME="zsh"
elif [[ "$SHELL" == *"bash"* ]]; then
    SHELL_CONFIG="$HOME/.bashrc"
    SHELL_NAME="bash"
else
    echo "[FAIL] Unknown shell: $SHELL"
    echo "Manually add these to your shell config:"
    echo 'export ANTHROPIC_AUTH_TOKEN="God"'
    echo 'export ANTHROPIC_BASE_URL="http://localhost:16324"'
    exit 1
fi

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  ClaudeFree Environment Setup${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"

# Check if already configured
if grep -q "ANTHROPIC_AUTH_TOKEN.*God" "$SHELL_CONFIG" 2>/dev/null; then
    echo -e "${GREEN}[OK] Already configured!${NC}"
    echo -e "Environment variables found in: ${BLUE}$SHELL_CONFIG${NC}\n"

    if [ "$WRITE_ONLY" == "0" ]; then
        export ANTHROPIC_AUTH_TOKEN="God"
        export ANTHROPIC_BASE_URL="http://localhost:16324"
    fi

    echo -e "${GREEN}Current configuration:${NC}"
    echo -e "  ANTHROPIC_AUTH_TOKEN = ${YELLOW}God${NC}"
    echo -e "  ANTHROPIC_BASE_URL   = ${YELLOW}http://localhost:16324${NC}\n"

    if [ "$WRITE_ONLY" == "1" ]; then
        echo -e "${YELLOW}Run 'source $SHELL_CONFIG' to apply to this terminal.${NC}\n"
    fi
    return 0 2>/dev/null || exit 0
fi

# Create backup
if [ -f "$SHELL_CONFIG" ]; then
    cp "$SHELL_CONFIG" "$SHELL_CONFIG.backup"
    echo -e "${YELLOW}[CLIPBOARD] Backup created: $SHELL_CONFIG.backup${NC}\n"
fi

# Add configuration
cat >> "$SHELL_CONFIG" << 'EOF'

# ═══════════════════════════════════════════════════════════════
# ClaudeFree Configuration
# ═══════════════════════════════════════════════════════════════
export ANTHROPIC_AUTH_TOKEN="God"
export ANTHROPIC_BASE_URL="http://localhost:16324"
EOF

echo -e "${GREEN}[OK] Configuration added!${NC}\n"

# Export to current shell if sourced
if [ "$WRITE_ONLY" == "0" ]; then
    export ANTHROPIC_AUTH_TOKEN="God"
    export ANTHROPIC_BASE_URL="http://localhost:16324"
fi

echo -e "${GREEN}Configuration:${NC}"
echo -e "  Shell:                  ${YELLOW}$SHELL_NAME${NC}"
echo -e "  Config file:            ${YELLOW}$SHELL_CONFIG${NC}"
echo -e "  ANTHROPIC_AUTH_TOKEN:   ${YELLOW}God${NC}"
echo -e "  ANTHROPIC_BASE_URL:     ${YELLOW}http://localhost:16324${NC}\n"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}[OK] Setup Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"

echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Start the proxy server:"
echo -e "   ${YELLOW}claude-start-server${NC}\n"
echo -e "2. In another terminal, just run:"
echo -e "   ${YELLOW}claude${NC}\n"

if [ "$WRITE_ONLY" == "1" ]; then
    echo -e "${BLUE}Apply to current shell:${NC}  ${YELLOW}source setup-env.sh${NC}"
    echo -e "${BLUE}Or restart your terminal.${NC}\n"
fi
