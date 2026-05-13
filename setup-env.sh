#!/bin/bash
# setup-env.sh — Configure ANTHROPIC environment variables for Linux/macOS

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SHELL_CONFIG=""

# Detect shell
if [[ "$SHELL" == *"zsh"* ]]; then
    SHELL_CONFIG="$HOME/.zshrc"
    SHELL_NAME="zsh"
elif [[ "$SHELL" == *"bash"* ]]; then
    SHELL_CONFIG="$HOME/.bash_profile"
    SHELL_NAME="bash"
else
    echo "❌ Unknown shell: $SHELL"
    echo "Please manually add these lines to your shell config:"
    echo ""
    echo "export ANTHROPIC_AUTH_TOKEN=\"God\""
    echo "export ANTHROPIC_BASE_URL=\"http://localhost:16324\""
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
    echo -e "${GREEN}✅ Already configured!${NC}"
    echo -e "Environment variables found in: ${BLUE}$SHELL_CONFIG${NC}\n"
    source "$SHELL_CONFIG"
    echo -e "${GREEN}Current configuration:${NC}"
    echo -e "  ANTHROPIC_AUTH_TOKEN = ${YELLOW}$ANTHROPIC_AUTH_TOKEN${NC}"
    echo -e "  ANTHROPIC_BASE_URL   = ${YELLOW}$ANTHROPIC_BASE_URL${NC}\n"
    exit 0
fi

# Create backup
if [ -f "$SHELL_CONFIG" ]; then
    cp "$SHELL_CONFIG" "$SHELL_CONFIG.backup"
    echo -e "${YELLOW}📋 Backup created: $SHELL_CONFIG.backup${NC}\n"
fi

# Add configuration
cat >> "$SHELL_CONFIG" << 'EOF'

# ═══════════════════════════════════════════════════════════════
# ClaudeFree Configuration
# ═══════════════════════════════════════════════════════════════
export ANTHROPIC_AUTH_TOKEN="God"
export ANTHROPIC_BASE_URL="http://localhost:16324"
EOF

echo -e "${GREEN}✅ Configuration added!${NC}\n"

# Source the config
source "$SHELL_CONFIG"

# Verify
echo -e "${GREEN}Configuration Details:${NC}"
echo -e "  Shell:                  ${YELLOW}$SHELL_NAME${NC}"
echo -e "  Config file:            ${YELLOW}$SHELL_CONFIG${NC}"
echo -e "  ANTHROPIC_AUTH_TOKEN:   ${YELLOW}$ANTHROPIC_AUTH_TOKEN${NC}"
echo -e "  ANTHROPIC_BASE_URL:     ${YELLOW}$ANTHROPIC_BASE_URL${NC}\n"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"

echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Start the server in one terminal:"
echo -e "   ${YELLOW}uv run uvicorn server:app --host 0.0.0.0 --port 16324${NC}\n"
echo -e "2. In another terminal, just run:"
echo -e "   ${YELLOW}claude${NC}\n"

echo -e "${BLUE}Note:${NC} If variables don't work, restart your terminal or run:"
echo -e "  ${YELLOW}source $SHELL_CONFIG${NC}\n"
