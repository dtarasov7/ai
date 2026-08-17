require "sidekiq"
require "sidekiq/api"

redis_config = { url: ENV.fetch("REDIS_URL", "redis://redis:6379/0") }

Sidekiq.configure_client do |config|
  config.redis = redis_config
end

Sidekiq.configure_server do |config|
  config.redis = redis_config
  Yabeda::Prometheus::Exporter.start_metrics_server!
end
