FROM golang:1.24-alpine AS go-build

WORKDIR /src/go-backend
COPY go-backend/go.mod ./
RUN go mod download
COPY go-backend/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/qidian-gateway ./cmd/server

FROM node:20-alpine AS frontend-build

WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM alpine:3.21

RUN apk add --no-cache ca-certificates

WORKDIR /app
COPY --from=go-build /out/qidian-gateway /app/qidian-gateway
COPY --from=frontend-build /src/frontend/dist /app/frontend/dist

ENV HTTP_ADDR=:8000 \
    PYTHON_BASE_URL=http://python:8000 \
    STATIC_DIR=/app/frontend/dist

EXPOSE 8000

ENTRYPOINT ["/app/qidian-gateway"]
