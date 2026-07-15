require "bundler/gem_tasks"
require "rubocop/rake_task"
RuboCop::RakeTask.new

targeted_files = ARGV.drop(1)

require "rspec/core"
require "rspec/core/rake_task"

RSpec::Core::RakeTask.new(:spec) do |t|
  t.pattern = targeted_files unless targeted_files.empty?
end

RSpec.configure do |config|
  config.color = true
  config.formatter = :documentation
end

task default: %i[spec rubocop]

task "test:all" => :default do
  Dir.glob("gemfiles/Gemfile.rails-*.x") do |gemfile|
    puts RSpec::Core::Formatters::ConsoleCodes.wrap(gemfile, :cyan)
    sh({ "BUNDLE_GEMFILE" => gemfile }, "bundle", "install", "--quiet", "--retry=2", "--jobs=2")
    sh({ "BUNDLE_GEMFILE" => gemfile }, "bundle", "exec", "rspec")
  end
end
