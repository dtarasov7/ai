# Шаблон Zabbix для мониторинга Ceph

```xml
<?xml version="1.0" encoding="UTF-8"?>
<zabbix_export>
    <version>5.0</version>
    <date>2025-05-11T12:00:00Z</date>
    <groups>
        <group>
            <name>Templates/Applications</name>
        </group>
    </groups>
    <templates>
        <template>
            <template>Template Ceph Cluster Monitoring</template>
            <name>Template Ceph Cluster Monitoring</name>
            <description>Шаблон для мониторинга кластера Ceph с использованием Zabbix Agent 1</description>
            <groups>
                <group>
                    <name>Templates/Applications</name>
                </group>
            </groups>
            <applications>
                <application>
                    <name>Ceph Cluster</name>
                </application>
                <application>
                    <name>Ceph MON</name>
                </application>
                <application>
                    <name>Ceph MGR</name>
                </application>
                <application>
                    <name>Ceph OSD</name>
                </application>
                <application>
                    <name>Ceph RGW</name>
                </application>
                <application>
                    <name>HAProxy</name>
                </application>
                <application>
                    <name>Keepalived</name>
                </application>
            </applications>
            <items>
                <!-- Ceph Cluster Status -->
                <item>
                    <name>Ceph Cluster Health Status</name>
                    <key>ceph.cluster.status</key>
                    <delay>60s</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>TEXT</value_type>
                    <applications>
                        <application>
                            <name>Ceph Cluster</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{str(HEALTH_OK)}=0</expression>
                            <name>Ceph Cluster health is not OK</name>
                            <priority>HIGH</priority>
                            <description>Ceph cluster health status is not HEALTH_OK</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>Ceph Cluster Health Details</name>
                    <key>ceph.cluster.health_detail</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <value_type>TEXT</value_type>
                    <applications>
                        <application>
                            <name>Ceph Cluster</name>
                        </application>
                    </applications>
                </item>
                
                <!-- MON Service Items -->
                <item>
                    <name>Ceph MON Service Status</name>
                    <key>ceph.mon.status</key>
                    <delay>60s</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Ceph MON</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:ceph.mon.status.last()}=0</expression>
                            <name>Ceph MON service is not running on {$HOSTNAME}</name>
                            <priority>HIGH</priority>
                            <description>Ceph MON service is not active</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>Ceph MON Service Enabled</name>
                    <key>ceph.mon.enabled</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Ceph MON</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:ceph.mon.enabled.last()}=0</expression>
                            <name>Ceph MON service is not enabled on {$HOSTNAME}</name>
                            <priority>WARNING</priority>
                            <description>Ceph MON service is not set to start automatically on boot</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>Ceph MON Details</name>
                    <key>ceph.mon.details</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <value_type>TEXT</value_type>
                    <applications>
                        <application>
                            <name>Ceph MON</name>
                        </application>
                    </applications>
                </item>
                
                <!-- MGR Service Items -->
                <item>
                    <name>Ceph MGR Service Status</name>
                    <key>ceph.mgr.status</key>
                    <delay>60s</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Ceph MGR</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:ceph.mgr.status.last()}=0</expression>
                            <name>Ceph MGR service is not running on {$HOSTNAME}</name>
                            <priority>HIGH</priority>
                            <description>Ceph MGR service is not active</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>Ceph MGR Service Enabled</name>
                    <key>ceph.mgr.enabled</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Ceph MGR</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:ceph.mgr.enabled.last()}=0</expression>
                            <name>Ceph MGR service is not enabled on {$HOSTNAME}</name>
                            <priority>WARNING</priority>
                            <description>Ceph MGR service is not set to start automatically on boot</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>Ceph MGR Details</name>
                    <key>ceph.mgr.details</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <value_type>TEXT</value_type>
                    <applications>
                        <application>
                            <name>Ceph MGR</name>
                        </application>
                    </applications>
                </item>

                <!-- Discovery of OSD IDs -->
                <discovery_rule>
                    <name>OSD Discovery</name>
                    <key>ceph.osd.list</key>
                    <delay>1h</delay>
                    <item_prototypes>
                        <item_prototype>
                            <name>Ceph OSD {#OSD_ID} Service Status</name>
                            <key>ceph.osd.status[{#OSD_ID}]</key>
                            <delay>60s</delay>
                            <history>7d</history>
                            <trends>90d</trends>
                            <value_type>UNSIGNED</value_type>
                            <applications>
                                <application>
                                    <name>Ceph OSD</name>
                                </application>
                            </applications>
                            <trigger_prototypes>
                                <trigger_prototype>
                                    <expression>{$HOSTNAME:ceph.osd.status[{#OSD_ID}].last()}=0</expression>
                                    <name>Ceph OSD {#OSD_ID} service is not running on {$HOSTNAME}</name>
                                    <priority>HIGH</priority>
                                    <description>Ceph OSD {#OSD_ID} service is not active</description>
                                </trigger_prototype>
                            </trigger_prototypes>
                        </item_prototype>
                        <item_prototype>
                            <name>Ceph OSD {#OSD_ID} Service Enabled</name>
                            <key>ceph.osd.enabled[{#OSD_ID}]</key>
                            <delay>5m</delay>
                            <history>7d</history>
                            <trends>90d</trends>
                            <value_type>UNSIGNED</value_type>
                            <applications>
                                <application>
                                    <name>Ceph OSD</name>
                                </application>
                            </applications>
                            <trigger_prototypes>
                                <trigger_prototype>
                                    <expression>{$HOSTNAME:ceph.osd.enabled[{#OSD_ID}].last()}=0</expression>
                                    <name>Ceph OSD {#OSD_ID} service is not enabled on {$HOSTNAME}</name>
                                    <priority>WARNING</priority>
                                    <description>Ceph OSD {#OSD_ID} service is not set to start automatically on boot</description>
                                </trigger_prototype>
                            </trigger_prototypes>
                        </item_prototype>
                    </item_prototypes>
                </discovery_rule>
                
                <item>
                    <name>Ceph OSD Details</name>
                    <key>ceph.osd.details</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <value_type>TEXT</value_type>
                    <applications>
                        <application>
                            <name>Ceph OSD</name>
                        </application>
                    </applications>
                </item>
                
                <!-- RGW Service Items -->
                <item>
                    <name>Ceph RGW Service Status</name>
                    <key>ceph.rgw.status</key>
                    <delay>60s</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Ceph RGW</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:ceph.rgw.status.last()}=0</expression>
                            <name>Ceph RGW service is not running on {$HOSTNAME}</name>
                            <priority>HIGH</priority>
                            <description>Ceph RGW service is not active</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>Ceph RGW Service Enabled</name>
                    <key>ceph.rgw.enabled</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Ceph RGW</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:ceph.rgw.enabled.last()}=0</expression>
                            <name>Ceph RGW service is not enabled on {$HOSTNAME}</name>
                            <priority>WARNING</priority>
                            <description>Ceph RGW service is not set to start automatically on boot</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>Ceph RGW HTTP Status Code</name>
                    <key>ceph.rgw.http_check</key>
                    <delay>60s</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Ceph RGW</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:ceph.rgw.http_check.last()}&lt;200 or {$HOSTNAME:ceph.rgw.http_check.last()}&gt;=300</expression>
                            <name>Ceph RGW HTTP endpoint is not responding correctly on {$HOSTNAME}</name>
                            <priority>HIGH</priority>
                            <description>Ceph RGW HTTP endpoint did not return a 2xx status code</description>
                        </trigger>
                    </triggers>
                </item>
                
                <!-- HAProxy Items -->
                <item>
                    <name>HAProxy Service Status</name>
                    <key>haproxy.status</key>
                    <delay>60s</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>HAProxy</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:haproxy.status.last()}=0</expression>
                            <name>HAProxy service is not running on {$HOSTNAME}</name>
                            <priority>HIGH</priority>
                            <description>HAProxy service is not active</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>HAProxy Service Enabled</name>
                    <key>haproxy.enabled</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>HAProxy</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:haproxy.enabled.last()}=0</expression>
                            <name>HAProxy service is not enabled on {$HOSTNAME}</name>
                            <priority>WARNING</priority>
                            <description>HAProxy service is not set to start automatically on boot</description>
                        </trigger>
                    </triggers>
                </item>
                
                <!-- Keepalived Items -->
                <item>
                    <name>Keepalived Service Status</name>
                    <key>keepalived.status</key>
                    <delay>60s</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Keepalived</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:keepalived.status.last()}=0</expression>
                            <name>Keepalived service is not running on {$HOSTNAME}</name>
                            <priority>HIGH</priority>
                            <description>Keepalived service is not active</description>
                        </trigger>
                    </triggers>
                </item>
                <item>
                    <name>Keepalived Service Enabled</name>
                    <key>keepalived.enabled</key>
                    <delay>5m</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>UNSIGNED</value_type>
                    <applications>
                        <application>
                            <name>Keepalived</name>
                        </application>
                    </applications>
                    <triggers>
                        <trigger>
                            <expression>{$HOSTNAME:keepalived.enabled.last()}=0</expression>
                            <name>Keepalived service is not enabled on {$HOSTNAME}</name>
                            <priority>WARNING</priority>
                            <description>Keepalived service is not set to start automatically on boot</description>
                        </trigger>
                    </triggers>
                </item>
            </items>
        </template>
    </templates>
</zabbix_export>
```
