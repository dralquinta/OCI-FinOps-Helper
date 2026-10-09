#!/bin/bash
# Copyright (c) 2022 Oracle and/or its affiliates.
# All rights reserved. The Universal Permissive License (UPL), Version 1.0

# OCI Cost Report Collector v2.2.1 - Bash Wrapper

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PYTHON_SCRIPT="$SCRIPT_DIR/src/collector.py"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to log with timestamp and color
log() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $message"
}

log_info() {
    log "$BLUE" "$1"
}

log_success() {
    log "$GREEN" "$1"
}

log_error() {
    log "$RED" "$1"
}

log_warning() {
    log "$YELLOW" "$1"
}

log_action() {
    log "$CYAN" "$1"
}

# Function to detect and verify OCI CLI authentication
check_oci_auth() {
    log_action "============== Checking OCI Authentication =============="
    if oci iam region list --output table >/dev/null 2>&1; then
        log_success "✅ OCI CLI authentication working"
        return 0
    else
        log_error "❌ OCI CLI authentication failed"
        echo ""
        echo "Please ensure you have:"
        echo "  1. OCI CLI installed"
        echo "  2. Authentication configured (instance principal or config file)"
        echo ""
        return 1
    fi
}

# Function to setup Python virtual environment
setup_venv() {
    log_action ""
    log_action "============== Setting Up Python Environment =============="
    
    if [ -d "$VENV_DIR" ]; then
        log_success "✅ Virtual environment already exists"
    else
        log_info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        log_success "✅ Virtual environment created"
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip silently
    pip install --upgrade pip --quiet
    
    # Install required packages from requirements.txt
    log_info "Installing Python dependencies..."
    if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
    else
        log_warning "⚠️  requirements.txt not found, installing core dependencies only"
        pip install pandas requests --quiet
    fi
    
    if [ $? -eq 0 ]; then
        log_success "✅ Python dependencies installed"
    else
        log_error "❌ Failed to install Python dependencies"
        return 1
    fi
}

# Function to run the Python collector
run_collector() {
    log_action ""
    log_action "============== Running Collector =============="
    
    # Activate venv and run Python script
    source "$VENV_DIR/bin/activate"
    python3 "$PYTHON_SCRIPT" "$@"
    
    return $?
}

# Main execution
main() {
    # Help must work before authentication or environment setup.
    for argument in "$@"; do
        if [ "$argument" = "--help" ] || [ "$argument" = "-h" ]; then
            python3 "$PYTHON_SCRIPT" --help
            return 0
        fi
    done
    log_info "Starting OCI Cost Report Collector v2.2.1"
    
    # Validate arguments
    if [ $# -lt 4 ]; then
        log_error "Insufficient arguments"
        echo ""
        echo "OCI Cost Report Collector v2.2.1"
        echo ""
        echo "Usage: $0 <tenancy_ocid> <home_region> <from_date> <to_date> [OPTIONS]"
        echo "   or: $0 --tenancy-ocid <OCID> --home-region <REGION> --from <YYYY-MM-DD> --to <YYYY-MM-DD> [OPTIONS]"
        echo ""
        echo "Required Arguments:"
        echo "  tenancy_ocid  : OCI Tenancy OCID"
        echo "  home_region   : Home region (e.g., us-ashburn-1)"
        echo "  from_date     : Start date in YYYY-MM-DD format"
        echo "  to_date       : End date in YYYY-MM-DD format"
        echo ""
        echo "Optional Flags:"
        echo "  --only-recommendations  : Fetch only recommendations (fast, skips cost/usage)"
        echo "  --growth-collection     : Collect tags, FinOps inventory and Monitoring evidence (enabled by default)"
        echo "  --no-growth-collection  : Disable growth/FinOps collection"
        echo "  --only-growth           : Only run growth collection (skip cost/usage data)"
        echo "  --currency <CODE>       : Requested currency metadata; Advisor savings remain USD (no conversion)"
        echo "  --skip-cost             : Skip cost data collection"
        echo "  --skip-usage            : Skip usage data collection"
        echo "  --skip-enrichment       : Skip instance metadata enrichment"
        echo "  --skip-recommendations  : Skip recommendations collection"
        echo ""
        echo "Examples:"
        echo "  # Full collection"
        echo "  $0 ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-04"
        echo ""
        echo "  # Get only recommendations (fast)"
        echo "  $0 ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-04 --only-recommendations"
        echo ""
        echo "  # Growth collection only (tags and FinOps evidence)"
        echo "  $0 ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-04 --only-growth"
        echo ""
        echo "  # Full collection plus growth data"
        echo "  $0 ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-04 --growth-collection"
        echo ""
        echo "  # Requested currency metadata (Advisor savings stay USD)"
        echo "  $0 ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-04 --currency EUR"
        echo ""
        exit 1
    fi
    
    # Check OCI authentication
    check_oci_auth || exit 1
    
    # Setup virtual environment
    setup_venv || exit 1
    
    # Run the collector
    run_collector "$@"
    
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo ""
        echo "============== Execution Complete =============="
        echo "📁 Check the current directory for output files:"
        echo "   - output_merged.csv (if cost/usage collected)"
        echo "   - output.csv (if cost/usage collected)"
        echo "   - out.json (if cost/usage collected)"
        echo "   - instance_metadata.json (if cost/usage collected)"
        echo "   - recommendations.out (if recommendations collected)"
        echo "   - growth_collection_tags.json (if growth collection run)"
        echo "   - growth_collection_summary.txt (if growth collection run)"
        echo "   - finops_collection.json, finops_candidates.csv, finops_summary.txt (if growth collection run)"
    else
        echo ""
        echo "❌ Execution failed with exit code $exit_code"
    fi
    
    exit $exit_code
}

main "$@"
