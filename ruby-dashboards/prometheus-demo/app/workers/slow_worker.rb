class SlowWorker
  include Sidekiq::Job

  sidekiq_options queue: :slow, retry: 2

  def perform
    sleep(rand(0.20..0.80))
    Widget.count
  end
end

