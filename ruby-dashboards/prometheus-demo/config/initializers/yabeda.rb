Yabeda.configure do
  group :anycable_rpc do
    counter :call_count,
      comment: "Total number of simulated AnyCable RPC calls",
      tags: %i[method command status]

    histogram :call_runtime, tags: %i[method command status] do
      comment "Simulated AnyCable RPC call duration"
      unit :seconds
      buckets [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5]
    end
  end
end
