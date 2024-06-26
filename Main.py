import pygame
import sys
import os
import math
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

# The source for generating a track image can be found at: https://openprocessing.org/sketch/2307416

# Constants
TRACK_NAME = 'Track1.png'  # Filename for the track image
CAR_NAME = 'Car1.jpg'      # Filename for the car image
RAYS = 7                   # Number of rays for raycasting
SPREAD = 90                # Angular spread of rays in degrees

def scale_image_to_window(image, window_width, window_height):
    """
    Scales an image to fit within the specified dimensions of a window while preserving its aspect ratio.
    
    Args:
        image (pygame.Surface): The Pygame image to scale.
        window_width (int): The width of the window.
        window_height (int): The height of the window.

    Returns:
        pygame.Surface: The scaled image.
    """
    img_width, img_height = image.get_size()
    img_ratio = img_width / img_height
    window_ratio = window_width / window_height

    if img_ratio > window_ratio:
        scaled_width = window_width
        scaled_height = int(window_width / img_ratio)
    else:
        scaled_height = window_height
        scaled_width = int(window_height * img_ratio)

    return pygame.transform.scale(image, (scaled_width, scaled_height))

class Car(pygame.sprite.Sprite):
    """
    Represents a car controlled by both user input and an automated fuzzy logic system.
    
    Attributes:
        original_image (pygame.Surface): The original unscaled image of the car.
        image (pygame.Surface): The currently displayed image, which changes with rotation.
        rect (pygame.Rect): The rectangle area of the car image on the screen.
        speed (int): The speed of the car.
        angle (int): The current angle of the car in degrees.
        autopilot (bool): Whether the autopilot is active.
        distances (list[int]): Distances measured by rays for collision avoidance.
    """
    def __init__(self, image, initial_position):
        super().__init__()
        self.original_image = image
        self.image = image
        self.rect = self.image.get_rect(center=initial_position)
        self.speed = 10
        self.angle = 0
        self.autopilot = False
        self.distances = [0] * RAYS
        
        # Setup fuzzy control system for the car
        self.setup_fuzzy_control()

    @staticmethod
    def cast_ray(screen, start_pos, angle, max_distance=600):
        """
        Casts a ray from a starting position at a specified angle to detect collisions.
        
        Args:
            screen (pygame.Surface): The surface to draw and check for collisions.
            start_pos (tuple[int, int]): The starting position of the ray.
            angle (float): The angle at which the ray is cast, in degrees.
            max_distance (int): The maximum distance the ray should check for collision.

        Returns:
            int: The distance at which a collision is detected or the maximum distance if no collision is detected.
        """
        x, y = start_pos
        for distance in range(max_distance):
            dx = distance * math.cos(math.radians(angle))
            dy = distance * math.sin(math.radians(angle))
            nx, ny = int(x + dx), int(y - dy)  # Note that y is inverted in pygame
            if 0 <= nx < screen.get_width() and 0 <= ny < screen.get_height():
                color = screen.get_at((nx, ny))
                if color == (255, 255, 255, 255):  # Checking for white color collision
                    return distance
            else:
                break
        return max_distance  # Return max_distance if no collision detected

    def check_collision(self, screen):
        """
        Checks for collisions using raycasting from the car's front center and updates the distances array.
        Also, draws red laser lines indicating the direction and length of each ray.
        
        Args:
            screen (pygame.Surface): The screen on which to draw rays.
        """
        for i in range(RAYS):
            ray_angle = self.angle - SPREAD / 2 + (SPREAD / (RAYS - 1)) * i
            front_center = (self.rect.centerx + self.speed * math.cos(math.radians(self.angle)),
                            self.rect.centery - self.speed * math.sin(math.radians(self.angle)))
            distance = Car.cast_ray(screen, front_center, ray_angle)
            self.distances[i] = distance
            end_x = front_center[0] + distance * math.cos(math.radians(ray_angle))
            end_y = front_center[1] - distance * math.sin(math.radians(ray_angle))
            pygame.draw.line(screen, (255, 0, 0), front_center, (end_x, end_y), 2)

    def update(self):
        """
        Updates the car's position and orientation based on user input or autopilot control.
        
        Args:
            screen (pygame.Surface): The screen on which to perform updates, used for collision checks.
        """
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:  # Toggle autopilot on space press
            self.autopilot = not self.autopilot
        
        if not self.autopilot:
            if keys[pygame.K_LEFT]:
                self.angle += 5
            if keys[pygame.K_RIGHT]:
                self.angle -= 5

            self.image = pygame.transform.rotate(self.original_image, self.angle)
            self.rect = self.image.get_rect(center=self.rect.center)

            if keys[pygame.K_UP]:
                radians = math.radians(self.angle)
                self.rect.x += self.speed * math.cos(radians)
                self.rect.y -= self.speed * math.sin(radians)
            if keys[pygame.K_DOWN]:
                radians = math.radians(self.angle)
                self.rect.x -= self.speed * math.cos(radians)
                self.rect.y += self.speed * math.sin(radians)
        else:
            self.check_collision(screen)
            fuzzy_angle, fuzzy_speed = self.fuzzy_logic_controller()
            self.angle += fuzzy_angle
            self.image = pygame.transform.rotate(self.original_image, self.angle)
            self.rect = self.image.get_rect(center=self.rect.center)
            radians = math.radians(self.angle)
            self.rect.x += fuzzy_speed * math.cos(radians)
            self.rect.y -= fuzzy_speed * math.sin(radians)

    def setup_fuzzy_control(self):
        """
        Sets up the fuzzy control system for steering based on raycast distances.
        Defines input variables for each ray, output variable for steering, and the rules for the fuzzy system.
        """
        distance = np.arange(0, 601, 1)
        self.distances_input = [ctrl.Antecedent(distance, f'distance_{i}') for i in range(RAYS)]
        self.steering = ctrl.Consequent(np.arange(-90, 91, 1), 'steering')

        # Membership functions for all rays
        for dist in self.distances_input:
            self.setup_distance(dist)

        self.steering['hard_left'] = fuzz.trimf(self.steering.universe, [-90, -60, -30])
        self.steering['left'] = fuzz.trimf(self.steering.universe, [-45, -30, 0])
        self.steering['slight_left'] = fuzz.trimf(self.steering.universe, [-15, 0, 15])
        self.steering['straight'] = fuzz.trimf(self.steering.universe, [-10, 0, 10])
        self.steering['slight_right'] = fuzz.trimf(self.steering.universe, [-15, 0, 15])
        self.steering['right'] = fuzz.trimf(self.steering.universe, [0, 30, 45])
        self.steering['hard_right'] = fuzz.trimf(self.steering.universe, [30, 60, 90])

        rules = []

        for i, dist in enumerate(self.distances_input):
            angle_adjustment = (i - RAYS // 2) * 15  # scale and offset based on ray index
            if i < RAYS // 2:  # Rays to the left
                rules.append(ctrl.Rule(dist['close'], self.steering['right']))
                rules.append(ctrl.Rule(dist['medium'], self.steering['slight_right']))
            elif i > RAYS // 2:  # Rays to the right
                rules.append(ctrl.Rule(dist['close'], self.steering['left']))
                rules.append(ctrl.Rule(dist['medium'], self.steering['slight_left']))
            else:  # Center ray
                rules.append(ctrl.Rule(dist['close'], self.steering['hard_left' if angle_adjustment < 0 else 'hard_right']))

        self.steering_ctrl = ctrl.ControlSystem(rules)
        self.steering = ctrl.ControlSystemSimulation(self.steering_ctrl)

    def fuzzy_logic_controller(self):
        """
        Computes the steering angle and speed adjustments based on the fuzzy control system outputs.

        Returns:
            tuple(float, int): The steering adjustment angle and the current speed.
        """
        # Loop through all distances and set them as inputs for the fuzzy controller
        for i, dist in enumerate(self.distances):
            self.steering.input[f'distance_{i}'] = dist

        # Compute the decision
        self.steering.compute()
        steering_adjustment = self.steering.output['steering']

        return steering_adjustment, self.speed

    def setup_distance(self, distance_variable):
        """
        Configures the membership functions for a distance variable.

        Args:
            distance_variable (ctrl.Antecedent): The fuzzy antecedent variable for distance.
        """
        distance_variable['close'] = fuzz.trimf(distance_variable.universe, [0, 0, 100])
        distance_variable['medium'] = fuzz.trimf(distance_variable.universe, [50, 100, 400])
        distance_variable['far'] = fuzz.trimf(distance_variable.universe, [300, 600, 600])
            
    def draw(self, screen):
        """
        Draws the car's current image at its current position on the screen.

        Args:
            screen (pygame.Surface): The screen where the car should be drawn.
        """
        screen.blit(self.image, self.rect)

# Initialize and configure Pygame
pygame.init()
width, height = 1000, 800
screen = pygame.display.set_mode((width, height))
pygame.display.set_caption(TRACK_NAME.strip('.png'))

# Load images and create sprites
curdir = os.path.dirname(os.path.realpath(__file__))
track_image = pygame.image.load(os.path.join(curdir, 'Tracks', TRACK_NAME))
scaled_track = scale_image_to_window(track_image, width, height)
car_image = pygame.image.load(os.path.join(curdir, 'Cars', CAR_NAME)).convert_alpha()
scaled_car = scale_image_to_window(car_image, 80, 80)
car = Car(scaled_car, (width // 2, height // 2))

# Game main loop
running = True
clock = pygame.time.Clock()
while running:
    for event in pygame.event.get():
        if event.type is pygame.QUIT:
            running = False
    screen.fill((0, 0, 0))
    screen.blit(scaled_track, ((width - scaled_track.get_width()) // 2, (height - scaled_track.get_height()) // 2))
    car.update() 
    car.draw(screen)
    pygame.display.flip()
    clock.tick(15)

pygame.quit()
sys.exit()
