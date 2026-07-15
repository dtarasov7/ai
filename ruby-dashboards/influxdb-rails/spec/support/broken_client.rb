module InfluxDB
  module Rails
    module BrokenClient
      def build_broken_client(message = "message")
        client = double
        allow(client).to receive(:create_write_api).and_raise(message)
        client
      end
    end
  end
end
