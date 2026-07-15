$LOAD_PATH.unshift(File.join(File.dirname(__FILE__), "..", "lib"))
$LOAD_PATH.unshift(File.dirname(__FILE__))
require "active_support"
require_relative "../lib/influxdb/rails/helpers/rspec_matchers"
require File.expand_path("#{File.dirname(__FILE__)}/support/broken_client")
require "webmock/rspec"

WebMock.disable_net_connect!

ENV["RAILS_ENV"] ||= "test"

require "rails"

require "bundler/setup"
Bundler.require

puts "Loading Rails v#{Rails.version}..."

require "support/rails#{Rails::VERSION::MAJOR}/app"
require "rspec/rails"

require "pry"

RSpec.configure do |config|
  # use expect syntax
  config.disable_monkey_patching!
  config.infer_spec_type_from_file_location!

  config.after do
    travel_back
  end

  config.include ActiveSupport::Testing::TimeHelpers
  config.include ActiveSupport::Testing::Assertions
  config.include ActiveJob::TestHelper

  config.include InfluxDB::Rails::BrokenClient
end
