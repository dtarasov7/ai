require "#{File.dirname(__FILE__)}/../spec_helper"

RSpec.describe "Context" do
  it "resets the context after a request" do
    get "/metrics"

    expect_metric(
      tags: a_hash_including(
        location: "MetricsController#index",
        hook:     "sql",
        cached:   false
      )
    )

    expect(InfluxDB::Rails.current.tags).to be_empty
    expect(InfluxDB::Rails.current.fields).to be_empty
  end

  it "resets the context after a request when exceptioni occurs" do
    InfluxDB::Rails.client = build_broken_client

    capture_influxdb_output do
      get "/metrics"
    end

    expect_no_metric(hook: "process_action")
    expect(InfluxDB::Rails.current.tags).to be_empty
    expect(InfluxDB::Rails.current.fields).to be_empty
  end
end
