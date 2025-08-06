
# Исправление названия метрики falco_events

В DKP CSE 1.67.0 из-за обновлений версии falcosidekick, была переименованна метрика `falco_events` в `falcosecurity_falcosidekick_falco_events_total`.

По этой метрике в платформе настроен аллерт `GostChecksumValidationFailed` для модуля `gost-integrity-controller`.

Название аллерта будет поправлено в следующих релизах, в текущих кластерах DKP CSE 1.67.0 необходимо применить следующее исправление для `CustomPrometheusRules`:

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: CustomPrometheusRules
metadata:
  labels:
    app: prometheus
  name: falco-events-metrics-backward
spec:
  groups:
  - name: runtime-audit-engine.falco-metrics
    rules:
    - record: falco_events
      expr: falcosecurity_falcosidekick_falco_events_total{job="runtime-audit-engine"}
```
