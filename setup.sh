#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ═══════════════════════════════════════════════════════════════════════════════
# OS Detection
# ═══════════════════════════════════════════════════════════════════════════════

detect_os() {
    case "$(uname -s)" in
        Linux*)
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                if [ "$ID" = "fedora" ] || [ "$ID_LIKE" = "fedora" ]; then
                    echo "fedora"
                elif [ "$ID" = "ubuntu" ] || [ "$ID" = "debian" ] || [ "$ID_LIKE" = "debian" ]; then
                    echo "debian"
                elif [ "$ID" = "arch" ]; then
                    echo "arch"
                else
                    echo "linux"
                fi
            else
                echo "linux"
            fi
            ;;
        Darwin*)
            echo "macos"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "windows"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

OS=$(detect_os)

# Directories - Use project folder
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"
ENV_FILE="$SCRIPT_DIR/.env"

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  🚀 claudefree Setup${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Detected OS: $OS${NC}\n"

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Check/Install fzy
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "${BLUE}[1/4] Checking fzy installation...${NC}"

if ! command -v fzy &> /dev/null; then
    echo -e "${YELLOW}⚠️  fzy not found. Installing...${NC}"
    
    case "$OS" in
        fedora)
            echo -e "${YELLOW}📦 Installing fzy via dnf (Fedora)...${NC}"
            sudo dnf install -y fzy 2>/dev/null || {
                echo -e "${YELLOW}dnf installation failed, trying manual build...${NC}"
                INSTALL_MANUAL=1
            }
            ;;
        debian|ubuntu)
            echo -e "${YELLOW}📦 Installing fzy via apt (Debian/Ubuntu)...${NC}"
            sudo apt-get update && sudo apt-get install -y fzy 2>/dev/null || {
                echo -e "${YELLOW}apt installation failed, trying manual build...${NC}"
                INSTALL_MANUAL=1
            }
            ;;
        arch)
            echo -e "${YELLOW}📦 Installing fzy via pacman (Arch)...${NC}"
            sudo pacman -S fzy --noconfirm 2>/dev/null || {
                echo -e "${YELLOW}pacman installation failed, trying manual build...${NC}"
                INSTALL_MANUAL=1
            }
            ;;
        macos)
            echo -e "${YELLOW}📦 Installing fzy via brew (macOS)...${NC}"
            brew install fzy 2>/dev/null || {
                echo -e "${YELLOW}brew installation failed, trying manual build...${NC}"
                INSTALL_MANUAL=1
            }
            ;;
        *)
            echo -e "${YELLOW}Unknown OS, trying manual build...${NC}"
            INSTALL_MANUAL=1
            ;;
    esac
    
    # Manual build fallback
    if [ "$INSTALL_MANUAL" = "1" ]; then
        echo -e "${YELLOW}🔨 Building fzy from source...${NC}"
        TEMP_DIR=$(mktemp -d)
        cd "$TEMP_DIR"
        git clone https://github.com/jhawthorn/fzy.git || {
            echo -e "${RED}❌ Failed to clone fzy repository${NC}"
            rm -rf "$TEMP_DIR"
            exit 1
        }
        cd fzy
        make || {
            echo -e "${RED}❌ Failed to build fzy${NC}"
            cd - > /dev/null
            rm -rf "$TEMP_DIR"
            exit 1
        }
        sudo make install || {
            echo -e "${RED}❌ fzy installation failed. Please install manually:${NC}"
            echo -e "${YELLOW}   git clone https://github.com/jhawthorn/fzy.git${NC}"
            echo -e "${YELLOW}   cd fzy && make && sudo make install${NC}"
            cd - > /dev/null
            rm -rf "$TEMP_DIR"
            exit 1
        }
        cd - > /dev/null
        rm -rf "$TEMP_DIR"
    fi
    
    echo -e "${GREEN}✅ fzy installed successfully${NC}\n"
else
    echo -e "${GREEN}✅ fzy already installed${NC}\n"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 2. Check/Install claude
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "${BLUE}[2/4] Checking claude installation...${NC}"

if ! command -v claude &> /dev/null; then
    echo -e "${YELLOW}⚠️  claude not found. Installing...${NC}"
    curl -fsSL https://claude.ai/install.sh | bash || {
        echo -e "${RED}❌ claude installation failed${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ claude installed successfully${NC}\n"
else
    echo -e "${GREEN}✅ claude already installed${NC}\n"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Fetch providers and select one
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "${BLUE}[3/4] Fetching providers from models.dev...${NC}"

TEMP_API=$(mktemp)
curl -s https://models.dev/api.json > "$TEMP_API" || {
    echo -e "${RED}❌ Failed to fetch providers from models.dev${NC}"
    exit 1
}

echo -e "${GREEN}✅ Providers fetched${NC}\n"

# Extract provider names
PROVIDERS=$(jq -r 'keys[]' "$TEMP_API" | sort)

echo -e "${BLUE}Select a provider:${NC}"

# Try fzy first, fallback to numbered menu
if command -v fzy &> /dev/null && [ -t 0 ]; then
    SELECTED_PROVIDER=$(echo "$PROVIDERS" | fzy --prompt "Search provider: ")
else
    echo -e "${YELLOW}Using numbered menu${NC}\n"
    PROVIDER_ARRAY=($PROVIDERS)
    for i in "${!PROVIDER_ARRAY[@]}"; do
        echo "$((i+1)). ${PROVIDER_ARRAY[$i]}"
    done
    echo -n "Enter provider number: "
    read -r PROVIDER_NUM
    SELECTED_PROVIDER="${PROVIDER_ARRAY[$((PROVIDER_NUM-1))]}"
fi

if [ -z "$SELECTED_PROVIDER" ]; then
    echo -e "${RED}❌ No provider selected${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Selected provider: $SELECTED_PROVIDER${NC}\n"

# ═══════════════════════════════════════════════════════════════════════════════
# 4. Ask for API key (only if not already in .env)
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDER_UPPER=$(echo "$SELECTED_PROVIDER" | tr '[:lower:]' '[:upper:]')
API_KEY_VAR="${PROVIDER_UPPER}_API_KEY"

if [ -f "$ENV_FILE" ] && grep -q "^${API_KEY_VAR}=" "$ENV_FILE"; then
    echo -e "${GREEN}✅ API key already found in .env${NC}"
    API_KEY=$(grep "^${API_KEY_VAR}=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
else
    echo -e "${BLUE}Enter API key for $SELECTED_PROVIDER${NC}"
    echo -n "API key visible? (y/n): "
    read -r VISIBLE
    echo -n "API key: "

    if [ "$VISIBLE" = "y" ] || [ "$VISIBLE" = "Y" ]; then
        read -r API_KEY
    else
        read -rs API_KEY
        echo ""
    fi

    if [ -z "$API_KEY" ]; then
        echo -e "${RED}❌ API key cannot be empty${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ API key saved${NC}"
fi
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# 5. Fetch models and select for each tier
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "${BLUE}Fetching models for $SELECTED_PROVIDER...${NC}"

MODELS=$(jq -r ".\"$SELECTED_PROVIDER\".models | keys[]" "$TEMP_API" | sort)

if [ -z "$MODELS" ]; then
    echo -e "${RED}❌ No models found for $SELECTED_PROVIDER${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Models fetched${NC}\n"

# Convert to array
MODEL_ARRAY=($MODELS)
MODEL_COUNT=${#MODEL_ARRAY[@]}

echo -e "${BLUE}Available models (${MODEL_COUNT} total):${NC}\n"

select_model() {
    local tier=$1
    local MODEL_CHOICE
    local MODEL_NUM
    local CUSTOM_MODEL
    
    echo -e "${BLUE}Select model for $tier tier:${NC}" >&2
    echo "0. [SAME_AS_DEFAULT]" >&2
    echo "1. [CUSTOM_MODEL]" >&2
    
    # Show first 10 models, then option to see more
    local count=0
    for i in "${!MODEL_ARRAY[@]}"; do
        if [ "$count" -lt 10 ]; then
            echo "$((i+2)). ${MODEL_ARRAY[$i]}" >&2
            ((count++))
        else
            break
        fi
    done
    echo "... and $((MODEL_COUNT - 10)) more models" >&2
    echo "" >&2
    
    if command -v fzy &> /dev/null && [ -t 0 ]; then
        echo "Or search:" >&2
        MODEL_CHOICE=$(printf "[SAME_AS_DEFAULT]\n[CUSTOM_MODEL]\n%s\n" "$MODELS" | fzy --prompt "Search $tier model: ")
    else
        echo -n "Enter selection number (0-$((MODEL_COUNT+1))): " >&2
        read -r MODEL_NUM
        if [ "$MODEL_NUM" = "0" ]; then
            MODEL_CHOICE="[SAME_AS_DEFAULT]"
        elif [ "$MODEL_NUM" = "1" ]; then
            MODEL_CHOICE="[CUSTOM_MODEL]"
        elif [ "$MODEL_NUM" -ge 2 ] && [ "$MODEL_NUM" -lt $((MODEL_COUNT + 2)) ]; then
            MODEL_CHOICE="${MODEL_ARRAY[$((MODEL_NUM-2))]}"
        else
            echo -e "${RED}❌ Invalid selection${NC}" >&2
            select_model "$tier"
            return
        fi
    fi
    
    if [ "$MODEL_CHOICE" = "[CUSTOM_MODEL]" ]; then
        echo -n "Enter custom model name: " >&2
        read -r CUSTOM_MODEL
        echo "$CUSTOM_MODEL"
    elif [ "$MODEL_CHOICE" = "[SAME_AS_DEFAULT]" ]; then
        echo "[SAME_AS_DEFAULT]"
    else
        echo "$MODEL_CHOICE"
    fi
}

MODEL_DEFAULT=$(select_model "DEFAULT")
MODEL_OPUS=$(select_model "OPUS")
MODEL_SONNET=$(select_model "SONNET")
MODEL_HAIKU=$(select_model "HAIKU")

echo -e "${GREEN}✅ Models selected${NC}\n"

# ═══════════════════════════════════════════════════════════════════════════════
# 6. Save configuration
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "${BLUE}Saving configuration...${NC}"

# Create config.json
cat > "$CONFIG_FILE" <<EOF
{
  "provider": "$SELECTED_PROVIDER",
  "model_default": "$MODEL_DEFAULT",
  "model_opus": "$MODEL_OPUS",
  "model_sonnet": "$MODEL_SONNET",
  "model_haiku": "$MODEL_HAIKU"
}
EOF

# Create/append to .env in project folder
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" <<EOF
# claudefree credentials
${PROVIDER_UPPER}_API_KEY="$API_KEY"
ANTHROPIC_AUTH_TOKEN="fr"
EOF
else
    # Append if not already present
    if ! grep -q "^${PROVIDER_UPPER}_API_KEY=" "$ENV_FILE"; then
        echo "${PROVIDER_UPPER}_API_KEY=\"$API_KEY\"" >> "$ENV_FILE"
    fi
fi

chmod 600 "$ENV_FILE"

# Ensure .gitignore includes .env
if [ -f "$SCRIPT_DIR/.gitignore" ]; then
    if ! grep -q "^\.env$" "$SCRIPT_DIR/.gitignore"; then
        echo ".env" >> "$SCRIPT_DIR/.gitignore"
        echo -e "${YELLOW}ℹ️  Added .env to .gitignore${NC}"
    fi
else
    echo ".env" > "$SCRIPT_DIR/.gitignore"
    echo -e "${YELLOW}ℹ️  Created .gitignore with .env${NC}"
fi

echo -e "${GREEN}✅ Configuration saved${NC}"
echo -e "   Config: ${BLUE}$CONFIG_FILE${NC}"
echo -e "   Credentials: ${BLUE}$ENV_FILE${NC}"
echo -e "   ${YELLOW}⚠️  Make sure .env is in .gitignore!${NC}\n"

# Clean up
rm -f "$TEMP_API"

# ═══════════════════════════════════════════════════════════════════════════════
# 7. Success message
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}\n"

echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Start the proxy server:"
echo -e "   ${YELLOW}uv run uvicorn server:app --host 0.0.0.0 --port 16324${NC}"
echo -e ""
echo -e "2. In another terminal, connect claude client:"
echo -e "   ${YELLOW}ANTHROPIC_AUTH_TOKEN="God" ANTHROPIC_BASE_URL="http://localhost:16324" claude${NC}"
echo -e ""
echo -e "Configuration stored in: ${BLUE}$SCRIPT_DIR${NC}\n"
