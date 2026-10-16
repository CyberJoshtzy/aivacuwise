import asyncio
import sys

import websockets

token = sys.argv[1]


async def listen():
    uri = f"ws://127.0.0.1:8000/ws/dashboard?token={token}"
    async with websockets.connect(uri) as ws:
        print("Connected, waiting for updates... (Ctrl+C to stop)")
        while True:
            message = await ws.recv()
            print("Received:", message)


asyncio.run(listen())
