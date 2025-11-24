import socketio
from app.socket.controller import SocketController

def register_socket_events(sio: socketio.AsyncServer, app_state):
    """
    Registers Socket.IO event handlers by binding them to a Controller instance.
    """
    
    # Instantiate the controller with dependencies from app_state
    controller = SocketController(sio, app_state.redis)

    # Register event handlers explicitly
    sio.on("connect", controller.on_connect)
    sio.on("disconnect", controller.on_disconnect)
    
    # Register the join_game handler
    sio.on("join_game", controller.on_join_game)
