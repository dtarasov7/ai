require "#{File.dirname(__FILE__)}/../spec_helper"

RSpec.describe "Logger" do
  it "logs exception" do
    InfluxDB::Rails.client = build_broken_client("error message")

    out = capture_influxdb_output do
      get "/metrics"
    end

    expect(out).to include("error message")
  end
end
