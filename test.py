import asyncio
import logging
import websockets
import time

# --- Import your logger ---
# This assumes 'log_server.py' is in the parent directory of 'app'
try:
    from app.agents.flipkart.utills.logger import setup_logger
except ImportError:
    print("Error: Could not import 'setup_logger'.")
    print("Please make sure 'log_server.py' is in the directory *above* the 'app' folder.")
    import sys
    sys.exit(1)

# --- Configuration ---
HOST = "localhost"
PORT = 8765
CONNECTED_CLIENTS = set()

# The single queue that all loggers will write to
LOG_QUEUE = asyncio.Queue()

# --- WebSocket Server Logic (Unchanged) ---

async def log_distributor():
    """
    Waits for messages on the LOG_QUEUE and distributes them to all
    connected WebSocket clients.
    """
    while True:
        # Wait for a log message from the queue
        message = await LOG_QUEUE.get()
        
        # Iterate over a copy of the set, as clients might disconnect
        for client in list(CONNECTED_CLIENTS):
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                CONNECTED_CLIENTS.remove(client)
            except Exception as e:
                # Handle other potential send errors
                print(f"Error sending log to client: {e}")

async def websocket_handler(websocket, path):
    """
    Handles a new WebSocket connection.
    """
    # Get a logger for the server itself
    log = logging.getLogger("main_server") 
    
    CONNECTED_CLIENTS.add(websocket)
    log.info(f"New frontend client connected: {websocket.remote_address}")
    try:
        await websocket.wait_closed()
    finally:
        CONNECTED_CLIENTS.remove(websocket)
        log.info(f"Frontend client disconnected: {websocket.remote_address}")

# --- Background Task to Generate Logs ---

async def generate_amazon_logs():
    """A simple task to simulate 'amazon' automation logs."""
    log = logging.getLogger("amazon") # Get the 'amazon' logger
    count = 0
    while True:
        await asyncio.sleep(3) # Amazon logs every 3 seconds
        log.info(f"Amazon automation: Processing order {123 + count}")
        count += 1
        if count % 4 == 0:
            log.warning(f"Amazon automation: Low stock for item A-{count}")

async def generate_flipkart_logs():
    """A simple task to simulate 'flipkart' automation logs."""
    log = logging.getLogger("flipkart") # Get the 'flipkart' logger
    count = 0
    while True:
        await asyncio.sleep(5) # Flipkart logs every 5 seconds
        log.info(f"Flipkart automation: Updating price for item F-{987 + count}")
        count += 1
        if count % 3 == 0:
            log.error(f"Flipkart automation: Failed to update item F-{987 + count}")

# --- Main Setup and Run ---

async def main():
    
    # 1. Setup the loggers, passing the *same queue* to all of them
    #    This ensures all loggers send to the same websocket distributor.
    amazon_logger = setup_logger("amazon", queue=LOG_QUEUE)
    flipkart_logger = setup_logger("flipkart", queue=LOG_QUEUE)
    server_logger = setup_logger("main_server", queue=LOG_QUEUE)

    # 2. Start the log distributor task
    asyncio.create_task(log_distributor())

    # 3. Start the log generator tasks for your automations
    asyncio.create_task(generate_amazon_logs())
    asyncio.create_task(generate_flipkart_logs())

    # 4. Start the WebSocket server
    # DO THIS
    server = await websockets.serve(websocket_handler, HOST, PORT)
    server_logger.info(f"WebSocket Log Server started on ws://{HOST}:{PORT}")
    
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
