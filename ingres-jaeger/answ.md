To enable the OpenTelemetry integration using the Ingress-Nginx helm chart, just add these parameters:

controller:
  config:
    enable-opentelemetry: "true"
    opentelemetry-config: "/etc/nginx/opentelemetry.toml"
    opentelemetry-operation-name: "HTTP $request_method $service_name $uri"
    opentelemetry-trust-incoming-span: "true"
    otlp-collector-host: "otel-collector.grafana.svc.cluster.local"
    otlp-collector-port: "4317"
    otel-max-queuesize: "2048"
    otel-schedule-delay-millis: "5000"
    otel-max-export-batch-size: "512"
    otel-service-name: "nginx-proxy" # Opentelemetry resource name
    otel-sampler: "AlwaysOn" # Also: AlwaysOff, TraceIdRatioBased
    otel-sampler-ratio: "1.0"
    otel-sampler-parent-based: "false"





Ingress-Nginx OpenTelemetry directives
While the Ingress-Nginx controller documentation currently falls short, we found the required information in the module which is used for the OpenTelemetry part. It is located in the following GitHub project.

We were able to find the directives which are provided by the OpenTelemetry module. Especially the directive opentelemetry_attribute was very interesting for us. It allows us to add custom attributes to spans.

We configured the ingress controller to add these directives to each server block in the nginx config. The configuration example below is for the helm chart:

controller:
  config:
    server-snippet: |
      opentelemetry_attribute "ingress.namespace" "$namespace";
      opentelemetry_attribute "ingress.service_name" "$service_name";
      opentelemetry_attribute "ingress.name" "$ingress_name";
      opentelemetry_attribute "ingress.upstream" "$proxy_upstream_name";