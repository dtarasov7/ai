#!/bin/bash
#
# Script to check local RadosGW service (port 8443)
#

TIMEOUT=5

# Try to connect to local RadosGW service
if timeout $TIMEOUT curl -s -k https://localhost:8443 -o /dev/null; then
    echo "1" # Service is available
else
    echo "0" # Service is unavailable
fi
