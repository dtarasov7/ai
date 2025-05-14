#!/bin/bash
#
# Script to check RadosGW service via VIP (port 443)
#

# VIP address is passed as an argument
VIP=$1
TIMEOUT=5

if [ -z "$VIP" ]; then
    echo "Error: VIP address not provided"
    exit 1
fi

# Try to connect to RadosGW via VIP
if timeout $TIMEOUT curl -s -k https://$VIP:443 -o /dev/null; then
    echo "1" # VIP service is available
else
    echo "0" # VIP service is unavailable
fi
