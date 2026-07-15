require "prometheus_exporter/client"
require "prometheus_exporter/middleware"

PrometheusExporter::Client.default = PrometheusExporter::Client.new(
  host: ENV.fetch("PROMETHEUS_EXPORTER_HOST", "prometheus-exporter"),
  port: Integer(ENV.fetch("PROMETHEUS_EXPORTER_PORT", 9394))
)

Rails.application.middleware.unshift PrometheusExporter::Middleware

