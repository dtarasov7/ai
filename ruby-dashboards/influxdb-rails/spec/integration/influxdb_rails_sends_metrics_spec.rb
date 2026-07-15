require "#{File.dirname(__FILE__)}/../spec_helper"

RSpec.describe "InfluxDB Rails sends metrics" do
  it "does a HTTP request to InfluxDB server with correct tags and fields" do
    travel_to Time.zone.local(2018, 1, 1, 9, 0, 0)
    configure("bucket", "org")
    stub_hostname("hostname")
    request = write_request.with(
      query: hash_including(bucket: "bucket", org: "org", precision: "ms"),
      body:  "rails,hook=block_instrumentation,location=raw,name=name,server=hostname value=1i 1514797200000000000"
    )

    InfluxDB::Rails.instrument "name", fields: { value: 1 }

    assert_requested(request, times: 1)
  end

  private

  def configure(bucket, org)
    InfluxDB::Rails.configure do |config|
      config.client.token = "my-token"
      config.client.bucket = bucket
      config.client.org = org
      config.client.async = false
    end
  end

  def write_request
    stub_request(:post, "https://localhost:8086/api/v2/write")
  end

  def stub_hostname(name)
    allow(Socket).to receive(:gethostname).and_return(name)
  end
end
