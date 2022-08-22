# Copyright (c) 2021 Oracle and/or its affiliates.
# !/usr/bin/env bash
# All rights reserved. The Universal Permissive License (UPL), Version 1.0 as shown at http://oss.oracle.com/licenses/upl
# fireup.sh 
#
# Purpose: Main module which starts the application




__install_dependencies(){

    if [ ! -d "./venv" ] 
    then
        echo "venv not present. Creating.."
        echo '============== Virtual Environment Creation =============='
        python3 -m venv venv
        source venv/bin/activate

        echo '============== Upgrading pip3 =============='
        pip3 install --upgrade pip

        echo '============== Installing app dependencies =============='
        pip3 install -r requirements.txt
    fi

source "./venv/bin/activate"    
}



__start_collector(){
    python3 collector.py
}


__main__(){ 
    __install_dependencies
    __start_collector
}


__main__