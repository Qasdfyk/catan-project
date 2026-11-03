FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /gateway ./cmd/gateway
RUN CGO_ENABLED=0 go build -o /bots ./cmd/bots

FROM alpine:3.22
RUN adduser -D gateway
USER gateway
COPY --from=build /gateway /bots /usr/local/bin/
EXPOSE 8080
CMD ["gateway"]
