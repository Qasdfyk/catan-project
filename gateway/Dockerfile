FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /gateway ./cmd/gateway
RUN CGO_ENABLED=0 go build -o /bots ./cmd/bots

# The expert bot's engine: catan_expert from catan-analysis-engine, built from
# its public repository (ENGINE_REF picks a branch or tag).
FROM alpine:3.22 AS engine
RUN apk add --no-cache build-base cmake git linux-headers
ARG ENGINE_REF=main
RUN git clone --depth 1 --branch "$ENGINE_REF" https://github.com/Qasdfyk/catan-analysis-engine /engine
WORKDIR /engine
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCATAN_BUILD_TESTS=OFF -DCATAN_BUILD_BENCHMARKS=OFF \
    && cmake --build build --target catan_expert -j"$(nproc)"

# The bots service (docker compose builds this target), with the engine.
FROM alpine:3.22 AS bots
RUN apk add --no-cache libstdc++ && adduser -D gateway
USER gateway
COPY --from=build /bots /usr/local/bin/
COPY --from=engine /engine/build/tools/catan_expert /usr/local/bin/
COPY --from=engine /engine/data/elites.json /usr/local/share/catan/elites.json
ENV EXPERT_COMMAND="catan_expert --elites /usr/local/share/catan/elites.json --time-ms 1000 --threads 4"
CMD ["bots"]

# The gateway, the default target.
FROM alpine:3.22
RUN adduser -D gateway
USER gateway
COPY --from=build /gateway /bots /usr/local/bin/
EXPOSE 8080
CMD ["gateway"]
