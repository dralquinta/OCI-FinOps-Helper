#!/bin/bash
# Copyright (c) 2022 Oracle and/or its affiliates.
# All rights reserved. The Universal Permissive License (UPL), Version 1.0

# OCI Cost Report Collector v2.0 - Bash Wrapper

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PYTHON_SCRIPT="$SCRIPT_DIR/src/collector.py"

# Function to detect and verify OCI CLI authentication
check_oci_auth() {
    echo "============== Checking OCI Authentication =============="
    if oci iam region list --output table >/dev/null 2>&1; then
        echo "✅ OCI CLI authentication working"
        return 0
    else
        echo "❌ OCI CLI authentication failed"
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
    echo ""
    echo "============== Setting Up Python Environment =============="
    
    if [ -d "$VENV_DIR" ]; then
        echo "✅ Virtual environment already exists"
    else
        echo "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        echo "✅ Virtual environment created"
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip silently
    pip install --upgrade pip --quiet
    
    # Install required packages
    echo "Installing Python dependencies..."
    pip install pandas requests --quiet
    
    if [ $? -eq 0 ]; then
        echo "✅ Python dependencies installed"
    else
        echo "❌ Failed to install Python dependencies"
        return 1
    fi
}

# Function to run the Python collector
run_collector() {
    echo ""
    echo "============== Running Collector =============="
    
    # Activate venv and run Python script
    source "$VENV_DIR/bin/activate"
    python3 "$PYTHON_SCRIPT" "$@"
    
    return $?
}

# Main execution
main() {
    # Validate arguments
    if [ $# -lt 4 ]; then
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
