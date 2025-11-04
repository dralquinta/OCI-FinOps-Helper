#!/bin/bash
# Copyright (c) 2022 Oracle and/or its affiliates.
# All rights reserved. The Universal Permissive License (UPL), Version 1.0 as shown at http://oss.oracle.com/licenses/upl

# Enhanced script for OCI Cloud Shell compatibility

echo "============== OCI Cost Report Collector (Cloud Shell Enhanced) =============="

# Check if we're in Cloud Shell
if [ "$OCI_CLI_CLOUD_SHELL" = "true" ] || [ -f "/etc/oci_env" ]; then
    echo "✓ Detected OCI Cloud Shell environment"
    CLOUD_SHELL=true
else
    echo "ℹ Running in standard environment"
    CLOUD_SHELL=false
fi

# Function to install dependencies
install_dependencies() {
    echo "============== Installing Dependencies =============="
    
    # Check if pip3 is available
    if ! command -v pip3 &> /dev/null; then
        echo "pip3 not found. Installing python3-pip..."
        if [ "$CLOUD_SHELL" = "true" ]; then
            # In Cloud Shell, we might need to use different package management
            echo "Note: In Cloud Shell, some packages may already be installed"
        else
            # Try to install pip
            python3 -m ensurepip --default-pip 2>/dev/null || echo "Could not install pip automatically"
        fi
    fi
    
    # Install required packages
    echo "Installing required Python packages..."
    pip3 install --user requests pandas
    
    # In Cloud Shell, OCI CLI should already be available
    if [ "$CLOUD_SHELL" = "true" ]; then
        echo "✓ OCI CLI should be pre-installed in Cloud Shell"
        oci --version
    else
        # Try to install OCI SDK for local environments
        pip3 install --user oci
    fi
}

# Function to check dependencies
check_dependencies() {
    echo "============== Checking Dependencies =============="
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python3 is required but not installed"
        exit 1
    fi
    echo "✓ Python3: $(python3 --version)"
    
    # Check OCI CLI (should be available in Cloud Shell)
    if command -v oci &> /dev/null; then
        echo "✓ OCI CLI: $(oci --version 2>&1 | head -1)"
    else
        echo "⚠ OCI CLI not found"
    fi
    
    # Check Python packages
    python3 -c "import requests, pandas" 2>/dev/null && echo "✓ Required Python packages available" || {
        echo "⚠ Some Python packages missing, installing..."
        install_dependencies
    }
}

# Function to check authentication
check_auth() {
    echo "============== Checking Authentication =============="
    
    if [ "$CLOUD_SHELL" = "true" ]; then
        echo "Checking Cloud Shell authentication..."
        if oci iam region list --output table 2>/dev/null | head -5; then
            echo "✓ Cloud Shell authentication is working"
        else
            echo "❌ Cloud Shell authentication failed"
            echo "Try running: oci session authenticate"
            exit 1
        fi
    else
        echo "Checking local OCI configuration..."
        if [ -f "$HOME/.oci/config" ]; then
            echo "✓ OCI config file found"
            cat "$HOME/.oci/config" | grep -E "(region|tenancy)" || true
        else
            echo "❌ No OCI config file found at $HOME/.oci/config"
            echo "Please set up OCI CLI configuration first"
            exit 1
        fi
    fi
}

# Main execution
main() {
    # Check if sufficient arguments provided
    if [ $# -lt 4 ]; then
        echo "❌ Insufficient arguments provided"
        echo ""
        echo "Usage: $0 tenancy_ocid home_region from_date to_date"
        echo "Example: $0 ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq us-ashburn-1 2025-11-01 2025-11-04"
        echo ""
        echo "Environment Information:"
        echo "  Cloud Shell: $CLOUD_SHELL"
        if [ "$CLOUD_SHELL" = "true" ]; then
            echo "  Authentication: Automatic (Cloud Shell)"
        else
            echo "  Authentication: ~/.oci/config file"
        fi
        exit 1
    fi
    
    # Check dependencies
    check_dependencies
    
    # Check authentication
    check_auth
    
    echo ""
    echo "============== Running Cost Report Collection =============="
    echo "Tenancy OCID: $1"
    echo "Region: $2"
    echo "From Date: $3"
    echo "To Date: $4"
    echo "Cloud Shell Mode: $CLOUD_SHELL"
    echo ""
    
    # Run the Python script
    python3 collector_cloudshell.py "$1" "$2" "$3" "$4"
    
    # Check if output files were created
    if [ -f "output.csv" ] && [ -f "out.json" ]; then
        echo ""
        echo "============== Success! =============="
        echo "✅ Cost report generated successfully!"
        echo "📊 Output files:"
        ls -lh output.csv out.json
        echo ""
        echo "💡 Tips:"
        echo "  - Use 'head -10 output.csv' to preview the data"
        echo "  - Download files using Cloud Shell's download feature"
        echo "  - Import output.csv into Excel or Google Sheets for analysis"
    else
        echo ""
        echo "❌ Output files not found. Check the error messages above."
        exit 1
    fi
}

# Run main function with all arguments
main "$@"