# LND Gotify Notifier 🚀⚡

A Python script that connects to your Lightning Network Daemon (LND) node and sends real-time notifications to a Gotify server for important events like channel openings, closings, settled invoices, and payment forwards.

**Use https://github.com/Primexz/lndnotify instead!**

## Features

- **Real-time notifications** for LND events
- **Channel events**: Get notified when channels open or close
- **Invoice events**: Get notified when invoices are settled
- **Forwarding events**: Get notified on successful payment forwards and see earned fees
- **Docker support** for easy deployment
- **Graceful shutdown** handling
- **Automatic reconnection** on connection failures
- **Comprehensive logging**

## Quick Start

### Using Docker Compose (Recommended)

1. Clone this repository:
```bash
git clone <repository-url>
cd lnd-gotify-notifier
```

2. Create a `.env` file with your configuration:
```env
GOTIFY_URL=https://your-gotify-server.com
GOTIFY_TOKEN=your-gotify-app-token
LND_GRPC_HOST=your-lnd-host:10009
LND_DIR=/path/to/your/lnd/data/directory
```

3. Run with Docker Compose:
```bash
docker-compose up -d
```

### Using Docker

1. Build the Docker image:
```bash
docker build -t lnd-gotify-notifier .
```

2. Run the container:
```bash
docker run -d \
  --name lnd-gotify-notifier \
  --restart unless-stopped \
  -e GOTIFY_URL=https://your-gotify-server.com \
  -e GOTIFY_TOKEN=your-gotify-app-token \
  -e LND_GRPC_HOST=your-lnd-host:10009 \
  -e LND_MACAROON_PATH=/lnd/gotify_notifier.macaroon \
  -e LND_TLS_CERT_PATH=/lnd/tls.cert \
  -v /path/to/your/lnd/data:/lnd:ro \
  lnd-gotify-notifier
```

### Manual Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Generate LND protobuf files:
```bash
mkdir -p lnrpc
curl -o lnrpc/lightning.proto https://raw.githubusercontent.com/lightningnetwork/lnd/master/lnrpc/lightning.proto
python -m grpc_tools.protoc -I./lnrpc --python_out=. --grpc_python_out=. lnrpc/lightning.proto
```

3. Set environment variables and run:
```bash
export GOTIFY_URL=https://your-gotify-server.com
export GOTIFY_TOKEN=your-gotify-app-token
export LND_GRPC_HOST=localhost:10009
export LND_MACAROON_PATH=/path/to/gotify_notifier.macaroon
export LND_TLS_CERT_PATH=/path/to/tls.cert
python gotify_notifier.py
```

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GOTIFY_URL` | URL of your Gotify server | - | ✅ |
| `GOTIFY_TOKEN` | Gotify application token | - | ✅ |
| `LND_GRPC_HOST` | LND gRPC host and port | `localhost:10009` | ✅ |
| `LND_MACAROON_PATH` | Path to LND macaroon file | - | ✅ |
| `LND_TLS_CERT_PATH` | Path to LND tls.cert file | - | ✅ |
| `LOGURU_LOG_LEVEL` | Log level (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` | ❌ |

### Gotify Setup

1. Install Gotify server
2. Create a new application in Gotify web interface
3. Copy the application token for the `GOTIFY_TOKEN` environment variable

### LND Setup

Make sure your LND node is running and accessible. You'll need:
- A macaroon file (for authentication)
- `tls.cert` file (for TLS connection)

These files are typically located in your LND data directory:
- Linux: `~/.lnd/`
- macOS: `~/Library/Application Support/Lnd/`
- Windows: `%APPDATA%\Lnd\`

#### Creating a Restricted Macaroon (Recommended)

For enhanced security, it is highly recommended to create a dedicated, read-only macaroon for this notifier instead of using the default `admin.macaroon`. This ensures the application has only the minimum required permissions.

Use `lncli` to create a new macaroon with these permissions:

```bash
docker exec -it lnd lncli bakemacaroon \
    --save_to=/.lnd/data/chain/bitcoin/mainnet/gotify_notifier.macaroon \
    info:read \
    invoices:read \
    uri:/lnrpc.Lightning/ListChannels \
    uri:/lnrpc.Lightning/SubscribeChannelEvents \
    uri:/lnrpc.Lightning/SubscribeInvoices \
    uri:/lnrpc.Lightning/ForwardingHistory \
    offchain:read
```

**Important:**
- Replace `/.lnd/data/chain/bitcoin/mainnet/` with the actual path inside your LND container.
- Update your `LND_MACAROON_PATH` environment variable to point to this new `gotify_notifier.macaroon` file.


## Notification Types

The notifier sends different types of notifications:

### 🚀 Startup Notification
Sent when the notifier starts successfully.

### ⚡ Channel Opened
Sent when a new channel is opened with another node.
- Includes remote node public key
- Shows channel capacity in sats

### 🔒 Channel Closed
Sent when a channel is closed.
- Includes remote node public key
- Shows channel capacity in sats

### 💰 Invoice Settled
Sent when an invoice is paid.
- Shows amount received in sats
- Includes memo if present

### ⚡ Payment Forwarded
Sent when a payment is successfully forwarded through your node.
- Shows the forwarded amount in sats
- Shows the fee earned in sats

### ❌ Error Notifications
Sent when unexpected errors occur (high priority).

## Monitoring and Logs

### Docker Logs
```bash
docker logs -f lnd-gotify-notifier
```

## License

MIT License
