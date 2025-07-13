# syntax=docker/dockerfile:1

# --- Build Stage ---
FROM python:3.12-slim AS builder

# Install build-time dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python build dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user grpcio-tools

# Create directory for generated protobuf files
RUN mkdir -p /app/lnrpc

# Download and generate LND protobuf files
RUN curl -o /app/lnrpc/lightning.proto https://raw.githubusercontent.com/lightningnetwork/lnd/master/lnrpc/lightning.proto &&     python -m grpc_tools.protoc     -I/app     --python_out=/app     --grpc_python_out=/app     lnrpc/lightning.proto

# --- Final Stage ---
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy generated protobuf files from the build stage
COPY --from=builder /app/lnrpc /app/lnrpc

# Copy the main script
COPY gotify_notifier.py .

# Create non-root user for security
RUN groupadd -r lndnotifier && useradd -r -g lndnotifier lndnotifier
RUN chown -R lndnotifier:lndnotifier /app
USER lndnotifier



# Run the script
CMD ["python", "-u", "gotify_notifier.py"]