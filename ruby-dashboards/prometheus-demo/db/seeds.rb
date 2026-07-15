20.times do |index|
  Widget.find_or_create_by!(name: "widget-#{index + 1}")
end

