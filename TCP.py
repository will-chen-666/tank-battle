import socket
import threading
import random
import os
import TCP_helper
import sys
sys.path.insert(0, os.path.abspath('./tank-war-game/src'))
import game
import struct
import time

# Import GameServer class
from game_server import GameServer  
# List to store connected clients
connected_clients = []
game_instance = None
game_instance_initialized = threading.Event()
ID_list = []
my_id = None


def broadcast_message(message, sender_conn):
    """Function to broadcast a message to all connected clients except the sender."""
    for conn, addr in connected_clients:
        if conn != sender_conn:
            try:
                conn.sendall(message)
            except Exception as e:
                print(f"Error sending message to {addr}: {e}")

def broadcast_message_to_all(message):
    """Function to broadcast a message to all connected clients."""
    for conn, addr in connected_clients:
        try:
            conn.sendall(message)
        except Exception as e:
            print(f"Error sending message to {addr}: {e}")

game_server = GameServer(broadcast_message_to_all, broadcast_message)


# Determines the system's local IP by creating a UDP socket
def getNodeIp():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]

def TCP_server( port=65432):
    host = getNodeIp()
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen()

        # Start the communicate with client thread
        communication_thread = threading.Thread(target=Server_Message_Sender)
        communication_thread.start()
        print("communication thread started")
        while True:
            print("server listener started")
            conn, addr = s.accept()
            client_thread = threading.Thread(target=Server_Listener, args=(conn, addr))
            client_thread.start()


def Server_Listener(conn, addr):
 
    """Function to listen to message from clients, each listener thread is created for each client."""
    print(f"Connected by {addr}")
    connected_clients.append((conn, addr))  # Add the client to the list of connected clients
    with conn:
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                else:
                    #return_message = TCP_helper.listener_process(data,conn)
                    # print(f"Received message from {addr}: {data}")
                    if data[0] <10:
                        #Here the add bullet have a broadcast message inside the function so we don't need to broadcast it again
                        #broadcast message that is not a 2 (shooting message)
                        #bug sometimes id is a large number being recieved put 1000 for now
                        if data[0] != 2 and data[1] < 1000:
                            broadcast_message(data, conn)
                            if data[0] == 1:
                                try:
                                    player_id, x, y, direction = struct.unpack('!IhhH', data[1:])
                                    game_server.move_player(player_id, x, y, direction)
                                    print(game_server.get_game_state())
                                except Exception as e:
                                    print(f"Error unpacking move message: {e}")
                        if data[0] == 2:
                            try:
                                shooter_id, x, y, direction = struct.unpack('!IhhH', data[1:])
                                game_server.add_bullet(shooter_id, x, y, direction)
                                print(game_server.get_game_state())
                            except Exception as e:
                                print(f"Error unpacking shoot message: {e}")

                    if data[0] == 11: # send out component's init message to client
                        try:
                            x=random.randint(100,700)
                            y=random.randint(100,500)
                            id = TCP_helper.generate_unique_id(ID_list)
                            message = struct.pack('!Biii', 12, x, y,id)
                            time.sleep(1)
                            conn.sendall(message)
                            game_server.add_player(id, x, y, 50, 50, 0)
                            game_server.send_wall_data()
                            print(game_server.get_game_state())
                            message = struct.pack('!Biii', 13, x, y, id)
                            broadcast_message(message, conn)
                            print(f"new client connected id{id} x{x} y{y}")
                        except Exception as e:
                            print(f"Error sending init message: {e}")
    
        except ConnectionResetError:
            print(f"Connection reset by {addr}")       
        finally:
            connected_clients.remove((conn, addr))  # Remove the client from the list when disconnected
            conn.close()
            print(f"connection closed successfully{addr}")




def Server_Message_Sender():
    """Function to send message to individual clients."""
    while True:
        if not connected_clients:
            continue

        server_input = input("Enter the client number to communicate with (-1 to exit):Example: 0:Hello World\n")

        if server_input == "-1":
            os._exit(0)

        try:
            client_index, message = server_input.split(":", 1)
            client_index = int(client_index)
        except ValueError:
            print("Invalid input format. Please use the format 'client_number:message'.")
            continue

        if client_index < 0 or client_index >= len(connected_clients):
            print("Invalid client number.")
            print("Connected clients:")
            for i, (client_conn, client_addr) in enumerate(connected_clients):
                print(f"{i}: {client_addr}")
            continue

        client_conn, client_addr = connected_clients[client_index]
        sender_ip = socket.gethostbyname(socket.gethostname())
        client_name = "Server"

        header = f"{sender_ip}|{client_name}|"
        full_message = header + message
        encoded_message = full_message.encode()
        prefix_byte = b'\x04'
        encoded_message = prefix_byte + encoded_message
        client_conn.sendall(encoded_message)

def Client_receive_messages(conn):
    """Function to receive messages from the server."""
    global game_instance
    global my_id
    while True:
        data = conn.recv(1)
        if not data:
            print("Connection was closed")
            break

        msg_type = data[0]
        if msg_type == 12:
            payload = TCP_helper.recv_chunks(conn, 12)
            if payload:
                receive_thread = threading.Thread(target=Client_receive_messages, args=(conn,))
                receive_thread.start()
                x, y, my_id = struct.unpack('!iii', payload)
                game_instance = game.Game(x, y, my_id, client_name)
                game_instance_initialized.set()  
                game_instance.run(conn)

        elif msg_type == 13:
            payload = TCP_helper.recv_chunks(conn, 12)  # '!iii'
            if payload:
                x, y, id = struct.unpack('!iii', payload)
                if id != my_id:
                    game_instance_initialized.wait()
                    print(f"New opponent connected: ID {id}, x {x}, y {y}")
                    game_instance.add_opponent(x, y, id)
        
                # Reveal my location to the opponent
                x, y = game_instance.tank.get_location()
                message = struct.pack('!Biii', 5, x, y, my_id)
                conn.sendall(message)

        elif msg_type == 5:
            payload = TCP_helper.recv_chunks(conn, 12)  # '!iii'
            if payload:
                x, y, id = struct.unpack('!iii', payload)
                game_instance_initialized.wait()
                if not game_instance.existing_opponent(id):
                    game_instance.add_opponent(x, y, id)
                    

        elif msg_type == 1:
            payload = TCP_helper.recv_chunks(conn, 10)
            if payload:
                id, x, y, direction = struct.unpack('!IhhH', payload)
                print(f"Movement message received: ID {id}, x {x}, y {y}, direction {direction}")
                game_instance_initialized.wait()
                game_instance.update_opponent(id, x, y, direction)

        elif msg_type == 2:
            payload = TCP_helper.recv_chunks(conn, 10)
            if payload:
                shooter_id, bullet_id, x, y, direction = struct.unpack('!hhhhh', payload)
                print(f"Shooting message received: ID {shooter_id}, bullet_id {bullet_id}, x {x}, y {y}, direction {direction}")
                game_instance_initialized.wait()
                game_instance.update_all_shooting(shooter_id, bullet_id, x, y, direction)

        #Handle powerup messages on client side
        elif msg_type == 20:
            payload = TCP_helper.recv_chunks(conn, 12)
            if payload:
                x,y, powerup_id = struct.unpack("!iii", payload)
                print(f"Powerup spawned at {x}, {y} with PID: {powerup_id}")

                powerup_type = ""
                if powerup_id == 1:
                    powerup_type = "speed"
                    
                elif powerup_id == 2:
                    powerup_type = "health"
                else:
                    print("something went wrong")
                    
                game_instance_initialized.wait()
                #draw powerup asset
                game_instance.create_powerup(x, y, powerup_type)

        elif msg_type == 21:
            payload = TCP_helper.recv_chunks(conn, 4)
            if payload:
                (player_id,) = struct.unpack("!i", payload)
                if player_id == my_id:
                    game_instance.activate_powerup_on_collision()
                    print("Power up achieved!")
                else:
                    game_instance.powerup.is_visible = False #hack
                    print(f"Another Player {player_id} collided with speed powerup")

        elif msg_type == 22:
            payload = TCP_helper.recv_chunks(conn, 4)
            if payload:
                (player_id,) = struct.unpack("!i", payload)
                if player_id == my_id:
                    game_instance.deactivate_powerup_on_timeout()
                    print(f"Power up over!")
                else:
                    print(f"Player {player_id} powerup is over")

                game_instance.powerup = None
            
                
   
        
        elif msg_type == 3:
            payload = TCP_helper.recv_chunks(conn, 6)
            if payload:
                player_hitter_id, player_hit_id, bullet_id= struct.unpack('!hhh', payload)
                print(f"Cannonball hit message received: player {player_hitter_id} hit player {player_hit_id} by bullet id {bullet_id}")
                game_instance_initialized.wait()
                game_instance.handle_cannonball_hit(player_hitter_id, player_hit_id, bullet_id)
        
        # Player eliminated message
        elif msg_type == 6:
            payload = TCP_helper.recv_chunks(conn, 4)
            if payload:
                player_hitter_id, player_id, = struct.unpack('!hh', payload)
                print(f"Player eliminated message received: player {player_id}")
                game_instance_initialized.wait()
                game_instance.handle_player_eliminated(player_hitter_id, player_id)

        elif msg_type == 7:
            payload = TCP_helper.recv_chunks(conn, 10)
            if payload:
                x, y, width, height, wall_id = struct.unpack('!hhhhh', payload)
                print(f"Wall data message received: x {x}, y {y}, width {width}, height {height}, wall_id {wall_id}")
                game_instance_initialized.wait()
                game_instance.handle_wall_data(x, y, width, height, wall_id)

        elif msg_type == 8:
            payload = TCP_helper.recv_chunks(conn, 2)
            if payload:
                bullet_id, = struct.unpack('!h', payload)
                print(f"Wall hit destroy message received: bullet_id {bullet_id}")
                game_instance_initialized.wait()
                game_instance.handle_wall_hit(bullet_id)
        
        elif msg_type == 9:
            payload = TCP_helper.recv_chunks(conn, 4)
            if payload:
                wall_id, bullet_id = struct.unpack('!hh', payload)
                print(f"Wall destroy message received: wall_id {wall_id}, bullet_id {bullet_id}")
                game_instance_initialized.wait()
                game_instance.handle_wall_destroy(wall_id, bullet_id)


def TCP_client(port=65432):
    global client_name
    input_string = False
    host = ""
    
    while input_string == False:    
        client_name = input("Enter your name: ")  # Prompt for sender name
        input_string = TCP_helper.validate_input(client_name)

    #checking for a valid server IP address
    input_string = False
    
    while input_string == False and host == "":
        host = input("Enter the game server IP you want to join: ")
        input_string = TCP_helper.validate_input(host)
    
    #sender_ip = socket.gethostbyname(socket.gethostname())
    #print(f"Sender IP address: {sender_ip}")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, int(port)))
    print("Connected to the server. Type 'exit' to quit.")

        # Start the receive messages thread
    #receive_thread = threading.Thread(target=Client_receive_messages, args=(s,))
    #receive_thread.start()

        # Start game by sending init message to server
    message = struct.pack('!B', 11)
    s.sendall(message)
    Client_receive_messages(s)
    """
    while True:
            message = input("Enter message: \n")
            if TCP_helper.validate_input(message) == False:
                print("No message can have use special charactor |.")
                continue
            if message.lower() == 'exit':
                print("Closing connection.")
                break
            
            # Add header to the message
            full_message = f"{client_name}|{message}"
            encoded_message = full_message.encode()
            prefix_byte = b'\x04'
            encoded_message = prefix_byte + encoded_message
            # Send the message
            s.sendall(encoded_message)
    """   

if __name__ == "__main__":
    role = input("Enter 'server' to start the server or 'client' to start the client: ").strip().lower()
    if role == 'server' or role == 's':
        TCP_server()
    elif role == 'client' or role == 'c':
        TCP_client()
    else:
        print("Invalid input. Please enter 'server' or 'client'.")
