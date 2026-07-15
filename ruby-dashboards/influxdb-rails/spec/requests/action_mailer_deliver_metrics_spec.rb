require "#{File.dirname(__FILE__)}/../spec_helper"

RSpec.describe "ActionMailer deliver metrics" do
  let(:tags_middleware) do
    lambda do |tags|
      tags.merge(tags_middleware: :tags_middleware)
    end
  end

  before do
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:ignored_environments).and_return(%w[development])
    allow_any_instance_of(ActionDispatch::Request).to receive(:request_id).and_return(:request_id)
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:application_name).and_return(:app_name)
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:tags_middleware).and_return(tags_middleware)
  end

  it "writes metric" do
    get "/metrics"

    expect_metric(
      tags:   a_hash_including(
        hook:   "deliver",
        mailer: "MetricMailer"
      ),
      fields: a_hash_including(
        additional_field: :value,
        request_id:       :request_id,
        value:            1
      )
    )
  end

  it "does not write metric when hook is ignored" do
    allow_any_instance_of(InfluxDB::Rails::Configuration).to receive(:ignored_hooks).and_return(["deliver.action_mailer"])

    get "/metrics"

    expect_no_metric(
      tags: a_hash_including(
        hook:   "deliver",
        mailer: "MetricMailer"
      )
    )
  end
end
