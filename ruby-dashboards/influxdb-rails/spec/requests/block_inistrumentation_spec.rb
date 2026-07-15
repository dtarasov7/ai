require "#{File.dirname(__FILE__)}/../spec_helper"

RSpec.describe "BlockInstrumentation metrics" do
  let(:tags_middleware) do
    lambda do |tags|
      tags.merge(tags_middleware: :tags_middleware)
    end
  end

  before do
    allow_any_instance_of(ActionDispatch::Request).to receive(:request_id).and_return(:request_id)
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:application_name).and_return(:app_name)
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:tags_middleware).and_return(tags_middleware)
  end

  it "writes metric" do
    get "/metrics"

    expect_metric(
      tags:   a_hash_including(
        hook:      "block_instrumentation",
        block_tag: :block_tag,
        name:      "name"
      ),
      fields: a_hash_including(
        additional_field: :value,
        request_id:       :request_id,
        block_field:      :block_value,
        value:            be_between(1, 500)
      )
    )
  end

  it "includes correct timestamps" do
    travel_to Time.zone.local(2018, 1, 1, 9, 0, 0)

    get "/metrics"

    expect_metric(
      tags: a_hash_including(
        location: "MetricsController#index",
        hook:     "block_instrumentation"
      ),
      time: Time.at(1_514_797_200)
    )
  end

  it "does not write metric when hook is ignored" do
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:ignored_hooks).and_return(["block_instrumentation.influxdb_rails"])

    get "/metrics"

    expect_no_metric(
      tags: a_hash_including(
        hook: "block_instrumentation"
      )
    )
  end
end
