FROM ruby:3.3-slim-bookworm

ENV BUNDLE_PATH=/usr/local/bundle \
    BUNDLE_WITHOUT=development:test \
    RAILS_ENV=production \
    RACK_ENV=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Gemfile ./
RUN bundle install --jobs=4 --retry=3

COPY . .
RUN chmod +x bin/rails

EXPOSE 3000 9394

CMD ["bundle", "exec", "rails", "server", "-b", "0.0.0.0", "-p", "3000"]

