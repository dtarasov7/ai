class FailingWorker
  include Sidekiq::Job

  sidekiq_options queue: :critical, retry: 2

  def perform
    raise "intentional Sidekiq failure for dashboard testing"
  end
end

