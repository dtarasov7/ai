require "sidekiq"
require "sidekiq/api"

redis_config = { url: ENV.fetch("REDIS_URL", "redis://redis:6379/0") }

class SidekiqMetricsBootstrap
  @mutex = Mutex.new

  class << self
    def start
      return if @started

      @mutex.synchronize do
        return if @started

        PrometheusExporter::Instrumentation::Process.start(type: "sidekiq")
        PrometheusExporter::Instrumentation::SidekiqProcess.start
        PrometheusExporter::Instrumentation::SidekiqQueue.start(all_queues: true)
        PrometheusExporter::Instrumentation::SidekiqStats.start
        @started = true
      end
    end
  end

  def call(_worker, _job, _queue)
    self.class.start
    yield
  end
end

Sidekiq.configure_client do |config|
  config.redis = redis_config
end

Sidekiq.configure_server do |config|
  config.redis = redis_config

  require "prometheus_exporter/instrumentation"

  config.server_middleware do |chain|
    chain.add SidekiqMetricsBootstrap
    chain.add PrometheusExporter::Instrumentation::Sidekiq
  end

  config.death_handlers << PrometheusExporter::Instrumentation::Sidekiq.death_handler

  config.on(:shutdown) do
    PrometheusExporter::Client.default.stop(wait_timeout_seconds: 10)
  end
end
