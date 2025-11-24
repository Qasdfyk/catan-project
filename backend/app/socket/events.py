import socketio
from fastapi import FastAPI
from app.socket.controller import SocketController

def register_socket_events(sio: socketio.AsyncServer, app_state):
    """
    Registers Socket.IO event handlers by binding them to a Controller instance.
    """
    
    # Instantiate the controller with dependencies from app_state
    # Assuming app_state.redis is already initialized in main.py lifespan
    controller = SocketController(sio, app_state.redis)

    # Register event handlers explicitly
    sio.on("connect", controller.on_connect)
    sio.on("disconnect", controller.on_disconnect)
    sio.on("create_test_game", controller.on_create_test_game)