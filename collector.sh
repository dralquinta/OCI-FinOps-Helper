#!/bin/bash
# Copyright (c) 2022 Oracle and/or its affiliates.
# All rights reserved. The Universal Permissive License (UPL), Version 1.0

# OCI Cost Report Collector v2.0 - Bash Wrapper

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
    
    # Install required packages
    log_info "Installing Python dependencies..."
    pip install pandas requests --quiet
    
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
    log_info "Starting OCI Cost Report Collector v2.0"
    
    # Validate arguments
    if [ $# -lt 4 ]; then
        log_error "Insufficient arguments"
        echo ""
        echo "OCI Cost Report Collector v2.0"
        echo ""
        echo "Usage: $0 <tenancy_ocid> <home_region> <from_date> <to_date>"
        echo ""
        echo "Arguments:"
        echo "  tenancy_ocid  : OCI Tenancy OCID"
        echo "  home_region   : Home region (e.g., us-ashburn-1)"
        echo "  from_date     : Start date in YYYY-MM-DD format"
        echo "  to_date       : End date in YYYY-MM-DD format"
        echo ""
        echo "Example:"
        echo "  $0 ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-04"
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
        echo "   - output_merged.csv"
        echo "   - output.csv"
        echo "   - out.json"
        echo "   - instance_metadata.json"
    else
        echo ""
        echo "❌ Execution failed with exit code $exit_code"
    fi
    
    exit $exit_code
}

main "$@"
