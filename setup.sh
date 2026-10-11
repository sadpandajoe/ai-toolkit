#!/bin/bash
#
# setup.sh - Install AI coding tools and dependencies
#
# Usage: ./setup.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Darwin*) OS_TYPE="macos" ;;
    Linux*)  OS_TYPE="linux" ;;
    *)       error "Unsupported OS: $OS"; exit 1 ;;
esac

info "Detected OS: $OS_TYPE"

# Homebrew changes the machine outside this toolkit, so its installer runs
# only after the user says yes at a terminal.
ensure_homebrew() {
    command -v brew &> /dev/null && return 0
    local answer=""
    if [[ -t 0 ]]; then
        read -r -p "Homebrew is not installed. Run the Homebrew installer from brew.sh now? [y/N] " answer
    fi
    if [[ ! "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        error "Homebrew is required to install $1 on macOS. Install it from https://brew.sh, then re-run ./setup.sh."
        exit 1
    fi
}

# Install a package with Homebrew (macOS) or apt/yum (Linux)
install_package() {
    local package=$1
    if [[ "$OS_TYPE" == "macos" ]]; then
        if ! command -v brew &> /dev/null; then
            ensure_homebrew "$package"
            warn "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add Homebrew to PATH for Apple Silicon
            if [[ -f "/opt/homebrew/bin/brew" ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -f "/usr/local/bin/brew" ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
        fi
        brew install "$package"
    elif [[ "$OS_TYPE" == "linux" ]]; then
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y "$package"
        elif command -v yum &> /dev/null; then
            sudo yum install -y "$package"
        else
            error "No supported package manager found"
            exit 1
        fi
    fi
}

# Check and install Node.js
install_node() {
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        info "Node.js already installed: $NODE_VERSION"
    else
        warn "Node.js not found. Installing..."
        if [[ "$OS_TYPE" == "macos" ]]; then
            install_package node
        elif command -v apt-get &> /dev/null; then
            # Debian/Ubuntu - NodeSource, current LTS line (24.x)
            curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
            sudo apt-get install -y nodejs
        elif command -v yum &> /dev/null; then
            # RHEL/CentOS/Fedora - NodeSource, current LTS line (24.x)
            curl -fsSL https://rpm.nodesource.com/setup_24.x | sudo bash -
            sudo yum install -y nodejs
        else
            error "No supported package manager found for Node.js"
            exit 1
        fi
        info "Node.js installed: $(node --version)"
    fi

    # Verify npm is available
    if ! command -v npm &> /dev/null; then
        error "npm not found after Node.js installation"
        exit 1
    fi
    info "npm available: $(npm --version)"
}

# Check and install Claude Code
install_claude_code() {
    if command -v claude &> /dev/null; then
        info "Claude Code already installed"
    else
        warn "Claude Code not found. Installing..."
        npm install -g @anthropic-ai/claude-code
        info "Claude Code installed"
    fi
}

# Check and install Codex CLI
install_codex() {
    if command -v codex &> /dev/null; then
        info "Codex CLI already installed"
    else
        warn "Codex CLI not found. Installing..."
        npm install -g @openai/codex
        info "Codex CLI installed"
    fi
}

# Check and install git (usually pre-installed)
install_git() {
    if command -v git &> /dev/null; then
        info "git already installed: $(git --version)"
    else
        warn "git not found. Installing..."
        install_package git
        info "git installed: $(git --version)"
    fi
}

# Main installation
main() {
    echo ""
    echo "========================================"
    echo "  AI Coding Environment Setup"
    echo "========================================"
    echo ""

    # Core dependencies
    info "Checking core dependencies..."
    install_git
    install_node

    echo ""

    # AI tools
    info "Installing AI coding tools..."
    install_claude_code
    install_codex

    # Optional dependencies
    echo ""
    info "Checking optional dependencies..."
    if command -v python3 &>/dev/null; then
        info "python3 available: $(python3 --version)"
    else
        warn "python3 not found. bin/aitk and the git guard need Python 3.11 or newer;"
        echo "  without it the git guard blocks git and gh commands."
    fi
    if command -v jq &>/dev/null; then
        info "jq already installed: $(jq --version)"
    else
        warn "jq not found (optional). The plan-drift and observation reminders stay silent without it."
        echo "  Install with: brew install jq (macOS) or apt-get install jq (Linux)"
    fi

    echo ""
    echo "========================================"
    echo "  Installation Complete!"
    echo "========================================"
    echo ""
    info "Installed tools:"
    echo "  - git:    $(git --version 2>/dev/null || echo 'not found')"
    echo "  - node:   $(node --version 2>/dev/null || echo 'not found')"
    echo "  - npm:    $(npm --version 2>/dev/null || echo 'not found')"
    echo "  - claude: $(command -v claude &>/dev/null && echo 'installed' || echo 'not found')"
    echo "  - codex:  $(command -v codex &>/dev/null && echo 'installed' || echo 'not found')"
    echo "  - python3: $(python3 --version 2>/dev/null || echo 'not found (required)')"
    echo "  - jq:     $(jq --version 2>/dev/null || echo 'not found (optional)')"
    echo ""
    info "API Key Setup:"
    echo "  - Claude: Run 'claude' and follow authentication prompts"
    echo "  - Codex:  export OPENAI_API_KEY=your-key-here"
    echo ""
    info "Next step: Run ./install.sh to set up Claude Code configuration"
    echo ""
}

main "$@"