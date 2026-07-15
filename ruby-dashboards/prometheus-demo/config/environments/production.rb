require "active_support/core_ext/integer/time"

Rails.application.configure do
  config.enable_reloading = false
  config.eager_load = true
  config.consider_all_requests_local = false
  config.server_timing = true
  config.force_ssl = false
  config.log_level = :info
  config.log_tags = [:request_id]
  config.logger = ActiveSupport::TaggedLogging.new(ActiveSupport::Logger.new($stdout))
  config.active_support.report_deprecations = false
  config.active_record.dump_schema_after_migration = false
  config.active_storage.service = :local
  config.secret_key_base = ENV.fetch("SECRET_KEY_BASE")
end

