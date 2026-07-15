class FastWorker
  include Sidekiq::Job

  sidekiq_options queue: :default, retry: 2

  def perform
    Widget.limit(1).pick(:id)
  end
end

