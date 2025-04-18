import sys
import os
import threading
import time
import math
import pygame
import struct
from Powerup import Powerup
import random
from pygame.locals import *
from settings import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, CANNONBALL_SPEED, wall_data

sys.path.insert(0, os.path.abspath('./tank-war-game/src'))

class GameServer:
    def __init__(self, broadcast_func_to_all, broadcast_func_to_client):
        self.broadcast_func_to_all = broadcast_func_to_all
        self.broadcast_func_except_sender = broadcast_func_to_client

        self.powerup = None
        self.powerup_respawn_delay = 10
        self.powerup_ready_to_respawn = False #if this is true, timer is set for next powerup spawn
        self.powerup_id = None
        
        self.players = {}  # {player_id: {"rect": pygame.Rect, "dir": int, "health": int}}
        self.bullets = {}  # {bullet_id: {"rect": pygame.Rect, "owner": player_id}}
        self.lock = threading.Lock()  # Ensures thread safety
        self.game_thread = threading.Thread(target=self.update_game_state, daemon=True)
        self.game_thread.start()  # Start the game loop in a background thread
        self.bullet_shot = 0
        self.wall = {i: {"rect": pygame.Rect(x, y, width, height), "health": 3} 
             for i, (x, y, width, height) in enumerate(wall_data)} # {wall_id: {"rect": pygame.Rect, "health": int}}

    def add_player(self, player_id, x, y, width, height, direction):
        """Add a new player safely using pygame.Rect for player position."""
        with self.lock:
            player_rect = pygame.Rect(x, y, width, height)
            self.players[player_id] = {"rect": player_rect, "dir": direction, "health": 1, "speed": 10,  "active_powerup": None, "powerup_timer": 0} 

            #tell every new player that there is a power up available
            if self.powerup is None:
                self.spawn_powerup()
            else:
                self.broadcast_powerup_state()

    def move_player(self, player_id, new_x, new_y, direction):
        """Move a player safely, updating their position in the Rect."""
        with self.lock:
            if player_id in self.players:
                self.players[player_id]["rect"].x = new_x
                self.players[player_id]["rect"].y = new_y
                self.players[player_id]["dir"] = direction

    #add a bullet to the game state and send it to all clients including the shooter 
    def add_bullet(self, shooter_id, x, y,  direction):
        """Add a new bullet safely using pygame.Rect for the bullet."""
        with self.lock:
            bullet_rect = pygame.Rect(x, y, 5, 5)  # Set the size of the bullet
            bullet_id = self.bullet_shot
            self.bullet_shot += 1
            self.bullets[bullet_id] = {"rect": bullet_rect, "owner": shooter_id, "bullet_direction": direction}
            msg_type=2
            packed_data = struct.pack('!Hhhhhh', msg_type, shooter_id, bullet_id, x, y, direction)
            self.broadcast_func_to_all(packed_data)

    def spawn_powerup(self):
        if self.powerup is None:
            
            powerup_types = ["speed", "health"]
            powerup_type = random.choice(powerup_types)

            if powerup_type == "speed":
                self.powerup_id = 1

            elif powerup_type == "health":
                self.powerup_id = 2

            
            x, y = random.randint(50, 50 + 650), random.randint(50, 50 + 650) #i couldn't find the variables related to the game board screen
            self.powerup = Powerup(x,y, powerup_type)

            print(f"Spawned {powerup_type} powerup at ({x}, {y})")
            self.broadcast_powerup_state()

    def broadcast_powerup_state(self):
        if self.powerup and self.powerup.is_visible:
            msg_type = 20
            packed_data = struct.pack("!Iiii", msg_type, self.powerup.x, self.powerup.y, self.powerup_id)
            self.broadcast_func_to_all(packed_data)


    def apply_power_up_effect(self, player_id, powerup_type):
        player = self.players[player_id]
        if powerup_type == "speed":
            player["speed"] *= 2

        if powerup_type == "health":
            player["health"] = 200000000000 #invincibility

        player["active_powerup"] = powerup_type
        player["powerup_timer"] = 10

        msg_type = 21
        packed_data = struct.pack("!Ii", msg_type, player_id)
        self.broadcast_func_to_all(packed_data)

    def deactivate_powerup_effect(self, player_id):
        player = self.players[player_id]
        if player["active_powerup"] == "speed":
            player["speed"] /= 2

        if player["active_powerup"] == "health":
            player["health"] = 1

        player["active_powerup"] = None
        player["powerup_timer"] = 0
        self.powerup = None
        msg_type = 22
        packed_data = struct.pack("!II", msg_type, player_id)
        self.broadcast_func_to_all(packed_data)
            

    def update_game_state(self):
        """Main game loop to update positions and check for collisions."""
        while True:
            with self.lock:
                # Move all bullets
                for bullet_id, bullet in list(self.bullets.items()):
                    direction = bullet["bullet_direction"]

                    # Update bullet position based on direction
                    if direction == 0:  # Up
                        bullet["rect"].y -= CANNONBALL_SPEED
                    elif direction == 4:  # Down
                        bullet["rect"].y += CANNONBALL_SPEED
                    elif direction == 6:  # Left
                        bullet["rect"].x -= CANNONBALL_SPEED
                    elif direction == 2:  # Right
                        bullet["rect"].x += CANNONBALL_SPEED
                    elif direction == 1:  # Up-Right
                        bullet["rect"].y -= CANNONBALL_SPEED / 1.414
                        bullet["rect"].x += CANNONBALL_SPEED / 1.414
                    elif direction == 7:  # Up-Left
                        bullet["rect"].y -= CANNONBALL_SPEED / 1.414
                        bullet["rect"].x -= CANNONBALL_SPEED / 1.414
                    elif direction == 3:  # Down-Right
                        bullet["rect"].y += CANNONBALL_SPEED / 1.414
                        bullet["rect"].x += CANNONBALL_SPEED / 1.414
                    elif direction == 5:  # Down-Left
                        bullet["rect"].y += CANNONBALL_SPEED / 1.414
                        bullet["rect"].x -= CANNONBALL_SPEED / 1.414

                    # Check if the bullet hits any player
                    for player_id, player in list(self.players.items()):
                        if player_id != bullet["owner"]:
                            #print(f"Player Rect: {player['rect']}, Bullet Rect: {bullet['rect']}")
                            collide = pygame.Rect.colliderect(bullet["rect"], player["rect"])
                            #print(f"Collision detected: {collide}")
                            
                            if collide:
                                print(f"Player {player_id} was hit by Player {bullet['owner']}! with bullet id {bullet_id}")
                                msg_type=3
                                player_hitter_id= bullet['owner']
                                player_hit_id= player_id
                                self.broadcast_func_to_all(struct.pack('!Hhhh', msg_type, player_hitter_id, player_hit_id, bullet_id))
                                player["health"] -= 1
                                del self.bullets[bullet_id]
                                if player["health"] <= 0:
                                    print(f"Player {player_id} has been eliminated!")
                                    del self.players[player_id]
                                    msg_type=6
                                    self.broadcast_func_to_all(struct.pack('!Hhh', msg_type, player_hitter_id, player_hit_id))
                                break  # Stop checking once bullet hits someone
                    
                    # Check if the bullet hits any wall
                    for wall_id, wall in list(self.wall.items()):
                        if pygame.Rect.colliderect(bullet["rect"], wall["rect"]):
                            print(f"Bullet {bullet_id} hit wall {wall_id}!")

                            # Reduce wall health
                            wall["health"] -= 1
                            msg_type=8
                            self.broadcast_func_to_all(struct.pack('!Hh', msg_type, bullet_id))
                            # Remove bullet
                            del self.bullets[bullet_id]

                            # If wall is destroyed, remove it and notify clients
                            if wall["health"] <= 0:
                                del self.wall[wall_id]
                                print(f"Wall {wall_id} destroyed!")
                                msg_type = 9
                                self.broadcast_func_to_all(struct.pack('!Hhh', msg_type, wall_id, bullet_id))

                            break  # Stop checking other walls since bullet is destroyed

                    # Remove bullets if they go off-screen
                    if bullet_id in self.bullets:  # Ensure the bullet wasn't removed in collision check
                        if bullet["rect"].x < 50 or bullet["rect"].x > 650+50 or bullet["rect"].y < 50 or bullet["rect"].y > 650+50:
                            del self.bullets[bullet_id]

            #checking for power-up collection by any player
            if self.powerup and self.powerup.is_visible:
                for player_id, player in self.players.items():
                    if self.powerup and self.powerup.rect.colliderect(player["rect"]):
                        print(f"Player {player_id} collected a {self.powerup.power_type} power-up")
                        self.apply_power_up_effect(player_id, self.powerup.power_type)
                        self.powerup.is_visible = False #why do we need this?
                        self.powerup = None #remove powerup as it has been consumed by player
                        

            #handle active powerup
            for player_id, player in self.players.items():
                if player["active_powerup"] is not None:
                    player["powerup_timer"] -= 1 /FPS

                    if player["powerup_timer"] <= 0:
                        self.deactivate_powerup_effect(player_id)
                        self.powerup_ready_to_respawn = True

            #powerup respawn
            if self.powerup_ready_to_respawn:
                self.powerup_respawn_delay -= 1 / FPS

                if self.powerup_respawn_delay <= 0:
                    self.powerup_ready_to_respawn = False
                    self.powerup_respawn_delay = 10 #set its original value for subsequent timing calculations
                    self.spawn_powerup()


                    
            time.sleep(1 / FPS)  # Maintain the game FPS (30 updates per second)

    def get_game_state(self):
        """Return a snapshot of the current game state (thread-safe)."""
        with self.lock:
            return self.players.copy(), self.bullets.copy()

    def send_wall_data(self):
        msg_type = 7
        for wall_id, wall in self.wall.items():
            rect = wall["rect"]  # `rect` is a pygame.Rect object
            x, y, width, height = rect.x, rect.y, rect.w, rect.h  # Extract properties correctly
            packed_data = struct.pack('!Hhhhhh', msg_type, x, y, width, height, wall_id)
            self.broadcast_func_to_all(packed_data)
