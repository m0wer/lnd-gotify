#!/usr/bin/env python3
"""
Gotify Notifier for LND Events.

This script connects to an LND node and sends notifications for channel
openings, closings, settled invoices, and forwards to a Gotify server.

Installation:
    pip install -r requirements.txt

Usage:
    - Set the following environment variables:
        GOTIFY_URL: The URL of your Gotify server (e.g., https://gotify.example.com)
        GOTIFY_TOKEN: Your Gotify application token.
        LND_GRPC_HOST: The gRPC host of your LND node (e.g., localhost:10009).
        LND_MACAROON_PATH: The path to your admin.macaroon file.
        LND_TLS_CERT_PATH: The path to your tls.cert file.

    - Run the script:
        python gotify_notifier.py
"""

import os
import requests
import threading
import time
import grpc
import codecs
import logging
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import generated protobuf files
try:
    import lnrpc.lightning_pb2 as ln
    import lnrpc.lightning_pb2_grpc as lnrpc
except ImportError:
    logger.error("Could not import lnd gRPC files. Please generate them from the lightning.proto file.")
    logger.error("Run: python -m grpc_tools.protoc -I/path/to/lnrpc --python_out=. --grpc_python_out=. lightning.proto")
    sys.exit(1)

# --- Configuration from Environment Variables ---
GOTIFY_URL = os.environ.get("GOTIFY_URL")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN")
LND_GRPC_HOST = os.environ.get("LND_GRPC_HOST", "localhost:10009")
LND_MACAROON_PATH = os.environ.get("LND_MACAROON_PATH")
LND_TLS_CERT_PATH = os.environ.get("LND_TLS_CERT_PATH")

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_requested = True

def send_gotify_notification(title, message, priority=5):
    """Sends a notification to the Gotify server."""
    if not GOTIFY_URL or not GOTIFY_TOKEN:
        logger.warning("Gotify URL or Token not configured. Skipping notification.")
        return

    try:
        response = requests.post(
            f"{GOTIFY_URL}/message",
            params={"token": GOTIFY_TOKEN},
            json={"title": title, "message": message, "priority": priority},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Successfully sent notification: {title}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending Gotify notification: {e}")

def get_lnd_stub():
    """Establishes a connection to the LND gRPC server and returns the stub."""
    if not all([LND_MACAROON_PATH, LND_TLS_CERT_PATH]):
        raise ValueError("LND macaroon and TLS cert paths must be set.")

    try:
        with open(LND_TLS_CERT_PATH, 'rb') as f:
            tls_cert = f.read()

        with open(LND_MACAROON_PATH, 'rb') as f:
            macaroon_bytes = f.read()
            macaroon = codecs.encode(macaroon_bytes, 'hex')

        def metadata_callback(context, callback):
            callback([('macaroon', macaroon)], None)

        ssl_creds = grpc.ssl_channel_credentials(tls_cert)
        auth_creds = grpc.metadata_call_credentials(metadata_callback)
        combined_creds = grpc.composite_channel_credentials(ssl_creds, auth_creds)

        channel = grpc.secure_channel(LND_GRPC_HOST, combined_creds)
        return lnrpc.LightningStub(channel)
    except Exception as e:
        logger.error(f"Failed to create LND stub: {e}")
        raise

def get_node_alias(pubkey, stub):
    """Fetches the alias of a node from its public key."""
    try:
        request = ln.NodeInfoRequest(pub_key=pubkey)
        response = stub.GetNodeInfo(request)
        return response.node.alias
    except grpc.RpcError as e:
        logger.error(f"Could not get node info for {pubkey}: {e.details()}")
        return pubkey

def subscribe_channel_events(stub):
    """Subscribes to channel events and sends notifications."""
    logger.info("Subscribing to channel events...")
    
    while not shutdown_requested:
        try:
            for event in stub.SubscribeChannelEvents(ln.ChannelEventSubscription()):
                if shutdown_requested:
                    break
                    
                if event.type == ln.ChannelEventUpdate.OPEN_CHANNEL:
                    pubkey = event.open_channel.remote_pubkey
                    capacity = event.open_channel.capacity
                    title = "⚡ Channel Opened"
                    message = f"New channel opened with node:\n{pubkey}\nCapacity: {capacity:,} sats"
                    send_gotify_notification(title, message)

                elif event.type == ln.ChannelEventUpdate.CLOSED_CHANNEL:
                    pubkey = event.closed_channel.remote_pubkey
                    capacity = event.closed_channel.capacity
                    title = "🔒 Channel Closed"
                    message = f"Channel with node closed:\n{pubkey}\nCapacity: {capacity:,} sats"
                    send_gotify_notification(title, message)
                    
        except grpc.RpcError as e:
            if shutdown_requested:
                break
            logger.error(f"gRPC error in channel subscription: {e.code()}: {e.details()}")
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                logger.info("LND unavailable, waiting 30 seconds before retrying...")
                time.sleep(30)
            else:
                time.sleep(10)
        except Exception as e:
            if shutdown_requested:
                break
            logger.error(f"Unexpected error in channel subscription: {e}")
            time.sleep(10)
    
    logger.info("Channel events subscription stopped")

def subscribe_invoices(stub):
    """Subscribes to invoice events and sends notifications."""
    logger.info("Subscribing to invoices...")
    
    while not shutdown_requested:
        try:
            for invoice in stub.SubscribeInvoices(ln.InvoiceSubscription()):
                if shutdown_requested:
                    break
                    
                if invoice.settled:
                    title = "💰 Invoice Settled"
                    message = f"Received {invoice.amt_paid_sat:,} sats"
                    if invoice.memo:
                        message += f"\nMemo: {invoice.memo}"
                    send_gotify_notification(title, message)
                    
        except grpc.RpcError as e:
            if shutdown_requested:
                break
            logger.error(f"gRPC error in invoice subscription: {e.code()}: {e.details()}")
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                logger.info("LND unavailable, waiting 30 seconds before retrying...")
                time.sleep(30)
            else:
                time.sleep(10)
        except Exception as e:
            if shutdown_requested:
                break
            logger.error(f"Unexpected error in invoice subscription: {e}")
            time.sleep(10)
    
    logger.info("Invoice subscription stopped")

def subscribe_forwards(stub):
    """Subscribes to forwarding events and sends notifications."""
    logger.info("Subscribing to forwarding events...")
    
    # Track processed forward events to avoid duplicates
    processed_forwards = set()
    last_forward_time = int(time.time())
    
    while not shutdown_requested:
        try:
            # Create a mapping from channel ID to peer pubkey
            channels = stub.ListChannels(ln.ListChannelsRequest()).channels
            chan_id_to_pubkey = {chan.chan_id: chan.remote_pubkey for chan in channels}
            
            current_time = int(time.time())
            request = ln.ForwardingHistoryRequest(
                start_time=last_forward_time,
                end_time=current_time,
                num_max_events=100
            )
            response = stub.ForwardingHistory(request)
            
            # Process events
            latest_timestamp = last_forward_time
            
            for event in response.forwarding_events:
                if shutdown_requested:
                    break
                
                # Create a unique identifier for this forward event
                event_id = f"{event.timestamp}_{event.chan_id_in}_{event.chan_id_out}_{event.amt_out}_{event.fee_msat}"
                
                if event_id in processed_forwards:
                    continue
                
                processed_forwards.add(event_id)
                
                # Update latest timestamp
                if event.timestamp > latest_timestamp:
                    latest_timestamp = event.timestamp
                
                # Get peer aliases
                in_pubkey = chan_id_to_pubkey.get(event.chan_id_in)
                out_pubkey = chan_id_to_pubkey.get(event.chan_id_out)
                
                in_peer_alias = get_node_alias(in_pubkey, stub) if in_pubkey else f"unknown channel ({event.chan_id_in})"
                out_peer_alias = get_node_alias(out_pubkey, stub) if out_pubkey else f"unknown channel ({event.chan_id_out})"
                
                # Calculate fee and ppm
                fee_msat = event.fee_msat
                ppm = (fee_msat * 1_000_000) // event.amt_out_msat if event.amt_out_msat > 0 else 0
                
                title = "⚡ Payment Forwarded"
                message = (
                    f"Forwarded {event.amt_out:,} sats\n"
                    f"From: {in_peer_alias}\n"
                    f"To:   {out_peer_alias}\n"
                    f"Fee:  {fee_msat} msat ({ppm} ppm)"
                )
                send_gotify_notification(title, message)
            
            # Update the last_forward_time to avoid reprocessing
            if latest_timestamp > last_forward_time:
                last_forward_time = latest_timestamp + 1
            
            # Clean up old processed forwards (keep only last 1000)
            if len(processed_forwards) > 1000:
                sorted_events = sorted(processed_forwards, key=lambda x: int(x.split('_')[0]))
                processed_forwards = set(sorted_events[-800:])
            
            # Sleep before the next poll
            time.sleep(30)
                
        except grpc.RpcError as e:
            if shutdown_requested:
                break
            logger.error(f"gRPC error in forward subscription: {e.code()}: {e.details()}")
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                logger.info("LND unavailable, waiting 30 seconds before retrying...")
                time.sleep(30)
            else:
                time.sleep(10)
        except Exception as e:
            if shutdown_requested:
                break
            logger.error(f"Unexpected error in forward subscription: {e}")
            time.sleep(10)
    
    logger.info("Forward subscription stopped")

def main():
    """Main function to start the notifier."""
    global shutdown_requested
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Validate configuration
    if not all([GOTIFY_URL, GOTIFY_TOKEN, LND_MACAROON_PATH, LND_TLS_CERT_PATH]):
        logger.error("Error: Required environment variables are not set.")
        logger.error("Required: GOTIFY_URL, GOTIFY_TOKEN, LND_MACAROON_PATH, LND_TLS_CERT_PATH")
        return 1

    logger.info("Starting Gotify LND Notifier...")
    logger.info(f"Gotify URL: {GOTIFY_URL}")
    logger.info(f"LND gRPC Host: {LND_GRPC_HOST}")
    
    # Send startup notification
    send_gotify_notification("🚀 LND Notifier Started", "The LND Gotify notifier is now running.")

    try:
        stub = get_lnd_stub()
        
        # Test connection
        try:
            info = stub.GetInfo(ln.GetInfoRequest())
            logger.info(f"Connected to LND node: {info.alias} (pubkey: {info.identity_pubkey})")
        except Exception as e:
            logger.error(f"Failed to connect to LND: {e}")
            return 1

        # Run subscriptions in separate threads
        channel_thread = threading.Thread(
            target=subscribe_channel_events, 
            args=(stub,), 
            daemon=True,
            name="ChannelEvents"
        )
        invoice_thread = threading.Thread(
            target=subscribe_invoices, 
            args=(stub,), 
            daemon=True,
            name="InvoiceEvents"
        )
        forward_thread = threading.Thread(
            target=subscribe_forwards,
            args=(stub,),
            daemon=True,
            name="ForwardEvents"
        )

        channel_thread.start()
        invoice_thread.start()
        forward_thread.start()

        logger.info("All subscriptions started successfully")

        # Keep the main thread alive
        while not shutdown_requested:
            time.sleep(1)

        logger.info("Waiting for threads to finish...")
        channel_thread.join(timeout=5)
        invoice_thread.join(timeout=5)
        forward_thread.join(timeout=5)
        
        send_gotify_notification("🛑 LND Notifier Stopped", "The LND Gotify notifier has been stopped.")
        logger.info("Notifier stopped successfully")
        return 0

    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        return 1
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        send_gotify_notification("❌ LND Notifier Error", f"An unexpected error occurred: {e}", priority=10)
        return 1

if __name__ == "__main__":
    sys.exit(main())
