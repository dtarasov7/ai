zabbix_export:
  version: '6.4'
  templates:
    - uuid: b0cd2e52687b4feaad4ffc0db6bac16c
      template: 'Ceph OSD'
      name: 'Ceph OSD'
      description: |
        Template for monitoring Ceph OSD services using Zabbix agent v1
        Compatible with Ceph 17.2.7 and Bluestore
      groups:
        - name: 'Templates/Applications'
      items: []
      discovery_rules:
        - uuid: 2c57adfd057e4c31bb05f9c7df9ae520
          name: 'Ceph OSD Discovery'
          type: ZABBIX_ACTIVE
          key: 'ceph.osd.discovery'
          delay: 1h
          lifetime: 1d
          item_prototypes:
            - uuid: bc9e1b0aed7343bab4e1301d12b442c9
              name: 'OSD {#OSDID} status'
              type: ZABBIX_ACTIVE
              key: 'ceph.osd.status[{#OSDID}]'
              delay: 1m
              history: 7d
              description: '0 - OSD не запущен, 1 - OSD запущен'
              valuemap:
                name: 'OSD Status'
              tags:
                - tag: component
                  value: osd
              trigger_prototypes:
                - uuid: 38d2b8b1a35d4ef2af5fa04b41c38d0b
                  expression: 'last(/Ceph OSD/ceph.osd.status[{#OSDID}])=0'
                  name: 'OSD {#OSDID} на {HOST.NAME} не запущен'
                  priority: HIGH
                  tags:
                    - tag: component
                      value: osd
                    - tag: scope
                      value: availability
            
            - uuid: 6faa64d0e4214ea1851fc3a57dd48bb7
              name: 'OSD {#OSDID} state'
              type: ZABBIX_ACTIVE
              key: 'ceph.osd.state[{#OSDID}]'
              delay: 2m
              history: 7d
              trends: '0'
              value_type: TEXT
              description: 'Состояние OSD (up/down, in/out)'
              tags:
                - tag: component
                  value: osd
              trigger_prototypes:
                - uuid: a7c9f52d91b84f1a8bedfed8b4992e4b
                  expression: 'find(/Ceph OSD/ceph.osd.state[{#OSDID}],,"like","down")=1'
                  name: 'OSD {#OSDID} на {HOST.NAME} в состоянии DOWN'
                  priority: HIGH
                  tags:
                    - tag: component
                      value: osd
                    - tag: scope
                      value: availability
                - uuid: 8f753fb5b4644d1f9ba7d84f05b39732
                  expression: 'find(/Ceph OSD/ceph.osd.state[{#OSDID}],,"like","out")=1'
                  name: 'OSD {#OSDID} на {HOST.NAME} в состоянии OUT'
                  priority: AVERAGE
                  tags:
                    - tag: component
                      value: osd
                    - tag: scope
                      value: availability
            
            - uuid: d5a2a72cf7c44edd87e00e0e50cc7214
              name: 'OSD {#OSDID} weight'
              type: ZABBIX_ACTIVE
              key: 'ceph.osd.weight[{#OSDID}]'
              delay: 5m
              history: 30d
              value_type: FLOAT
              description: 'Вес OSD в кластере CRUSH'
              tags:
                - tag: component
                  value: osd
            
            - uuid: 8b24c7d8b1fd4921986cb94c5b9e22a3
              name: 'OSD {#OSDID} used space'
              type: ZABBIX_ACTIVE
              key: 'ceph.osd.used_space[{#OSDID}]'
              delay: 5m
              history: 30d
              units: B
              description: 'Используемое пространство OSD'
              tags:
                - tag: component
                  value: osd
                - tag: scope
                  value: capacity
            
            - uuid: e19f7a8c80cb4c67955d9f4d89cfea5d
              name: 'OSD {#OSDID} total space'
              type: ZABBIX_ACTIVE
              key: 'ceph.osd.total_space[{#OSDID}]'
              delay: 5m
              history: 30d
              units: B
              description: 'Общее пространство OSD'
              tags:
                - tag: component
                  value: osd
                - tag: scope
                  value: capacity
            
            - uuid: f25c1d3a12474a4cafd2c9ad27f69b9e
              name: 'OSD {#OSDID} space utilization'
              type: CALCULATED
              key: 'ceph.osd.utilization[{#OSDID}]'
              delay: 5m
              history: 30d
              units: '%'
              params: '100*last("ceph.osd.used_space[{#OSDID}]")/last("ceph.osd.total_space[{#OSDID}]")'
              description: 'Процент использования пространства OSD'
              tags:
                - tag: component
                  value: osd
                - tag: scope
                  value: capacity
              trigger_prototypes:
                - uuid: e1c8beb3c2754d45baed0b7f9b6fab4a
                  expression: 'last(/Ceph OSD/ceph.osd.utilization[{#OSDID}])>90'
                  name: 'OSD {#OSDID} на {HOST.NAME} заполнен > 90%'
                  priority: WARNING
                  tags:
                    - tag: component
                      value: osd
                    - tag: scope
                      value: capacity
                - uuid: a8d9ac8fe9b242998dc5cd85932e07aa
                  expression: 'last(/Ceph OSD/ceph.osd.utilization[{#OSDID}])>95'
                  name: 'OSD {#OSDID} на {HOST.NAME} заполнен > 95%'
                  priority: HIGH
                  tags:
                    - tag: component
                      value: osd
                    - tag: scope
                      value: capacity
      
          graph_prototypes:
            - uuid: 63c9e7f20fcd4df3b15a4de1e6472dc7
              name: 'OSD {#OSDID} space usage'
              graph_items:
                - color: 1A7C11
                  item:
                    host: 'Ceph OSD'
                    key: 'ceph.osd.utilization[{#OSDID}]'
      
      valuemaps:
        - uuid: c2f3cc5e2a9b46b180da11fa8f4a57aa
          name: 'OSD Status'
          mappings:
            - value: '0'
              newvalue: 'Down'
            - value: '1'
              newvalue: 'Up'
