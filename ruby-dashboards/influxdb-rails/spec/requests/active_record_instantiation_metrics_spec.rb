require "#{File.dirname(__FILE__)}/../spec_helper"

RSpec.describe "ActiveRecord instantiation metrics" do
  let(:tags_middleware) do
    lambda do |tags|
      tags.merge(tags_middleware: :tags_middleware)
    end
  end
  let(:metric) { Metric.create!(name: "name") }

  before do
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:ignored_environments).and_return(%w[development])
    allow_any_instance_of(ActionDispatch::Request).to receive(:request_id).and_return(:request_id)
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:application_name).and_return(:app_name)
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:tags_middleware).and_return(tags_middleware)
  end

  it "writes metric" do
    get metric_path(metric)

    expect_metric(
      tags:   a_hash_including(
        hook:       "instantiation",
        class_name: "Metric"
      ),
      fields: a_hash_including(
        additional_field: :value,
        request_id:       :request_id,
        value:            be_between(1, 500),
        record_count:     1
      )
    )
  end

  it "includes correct timestamps" do
    travel_to Time.zone.local(2018, 1, 1, 9, 0, 0)

    get metric_path(metric)

    expect_metric(
      tags: a_hash_including(
        location: "MetricsController#show",
        hook:     "instantiation"
      ),
      time: Time.at(1_514_797_200)
    )
  end

  it "does not write metric when hook is ignored" do
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:ignored_hooks).and_return(["instantiation.active_record"])

    get metric_path(metric)

    expect_no_metric(
      tags: a_hash_including(
        hook: "instantiation"
      )
    )
  end
end
