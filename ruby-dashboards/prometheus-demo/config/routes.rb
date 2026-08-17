Rails.application.routes.draw do
  mount Yabeda::Prometheus::Exporter => "/metrics"

  get "/", to: "demo#index"
  get "/fast", to: "demo#fast"
  get "/slow", to: "demo#slow"
  get "/error", to: "demo#error"
  post "/jobs", to: "demo#enqueue"
  get "/health", to: "demo#health"
end
