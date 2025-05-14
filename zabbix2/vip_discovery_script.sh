#!/bin/bash
#
# Script to discover VIP address for RadosGW service
#

# VIP address defined in Zabbix macros
VIP=${1:-"$"} # Default to Zabbix macro if not specified

# Generate JSON for Zabbix discovery
cat << EOF
{
    "data": [
        {
            "{#VIP}": "$VIP"
        }
    ]
}
EOF
