class DemoController < ApplicationController
  def index
    render json: {
      service: "rails-prometheus-demo",
      endpoints: ["/fast", "/slow", "/error", "POST /jobs", "/health"]
    }
  end

  def fast
    names = Widget.order(id: :desc).limit(5).pluck(:name)
    render json: { result: "fast", widgets: names }
  end

  def slow
    sleep(rand(0.10..0.40))
    counts = 3.times.map { Widget.where("id >= ?", 1).count }
    render json: { result: "slow", counts: counts }
  end

  def error
    render json: { error: "intentional test response" }, status: :internal_server_error
  end

  def enqueue
    FastWorker.perform_async
    SlowWorker.perform_async
    FailingWorker.perform_async if params[:fail] == "1"
    render json: { queued: true, failing_job: params[:fail] == "1" }, status: :accepted
  end

  def health
    Widget.limit(1).pick(:id)
    render plain: "ok"
  end
end

