require_relative "boot"

require "rails/all"

Bundler.require(*Rails.groups)

module PrometheusDemo
  class Application < Rails::Application
    config.load_defaults 7.2
    config.api_only = true
    config.active_job.queue_adapter = :sidekiq
    config.hosts.clear
  end
end

