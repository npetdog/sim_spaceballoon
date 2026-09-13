import pygame
import sys
import random
import math
import bisect

pygame.init()
font = pygame.font.SysFont("Arial", 18)
info_font = pygame.font.SysFont("Arial", 20)

# ============================================================
# Window
# ============================================================

WIDTH = 1200
HEIGHT = 700

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("2D Earth Atmosphere Simulation")

clock = pygame.time.Clock()


# ============================================================
# Colors
# ============================================================

SPACE = (5, 5, 15)
EARTH = (40, 100, 200)
ATMOSPHERE = (255, 60, 60)


# ============================================================
# Earth
# ============================================================

EARTH_RADIUS = 6371.0          # km
ATMOSPHERE_HEIGHT = 1000.0     # km


# ============================================================
# Camera
# ============================================================

zoom = 0.08

MIN_ZOOM = 0.005
MAX_ZOOM = 5.0

DEFAULT_ZOOM = 0.05

camera_x = 0
camera_y = 0

dragging = False

# Middle mouse double-click detection
last_middle_click = 0
DOUBLE_CLICK_TIME = 300  # milliseconds


# ============================================================
# Hydrogen Weather Balloon Parameters
# ============================================================

BALLOON_PAYLOAD_MASS = 2.0       # kg
BALLOON_ENVELOPE_MASS = 1.2      # kg

# Diameter when inflated at launch
BALLOON_LAUNCH_DIAMETER = 2.0    # meters

# Approximate diameter at which envelope bursts
BALLOON_BURST_DIAMETER = 8.0     # meters

# Drag coefficient
# ~0.47 is sphere-like; real balloons can differ substantially
BALLOON_CD = 0.47

# Added/virtual mass coefficient
BALLOON_VIRTUAL_MASS_COEFF = 0.5

# Initial altitude
BALLOON_START_ALTITUDE = 0.0     # km

# Speed up simulation time
SIMULATION_SPEED = 100.0

# Hydrogen specific gas constant
R_HYDROGEN = 4124.0              # J / (kg K)

# Air specific gas constant
R_AIR = 287.05                   # J / (kg K)

G0 = 9.80665                     # m/s^2


# ============================================================
# Standard Atmosphere (for balloon physics)
# ============================================================

def atmosphere(altitude_km):

    h = max(0.0, altitude_km * 1000.0)

    # Layer definitions:
    # base altitude (m)
    # base temperature (K)
    # base pressure (Pa)
    # lapse rate (K/m)

    layers = [
        (0.0,     288.15, 101325.0,   -0.0065),
        (11000.0, 216.65, 22632.06,    0.0),
        (20000.0, 216.65, 5474.889,    0.001),
        (32000.0, 228.65, 868.0187,    0.0028),
        (47000.0, 270.65, 110.9063,    0.0),
        (51000.0, 270.65, 66.93887,   -0.0028),
        (71000.0, 214.65, 3.95642,    -0.002)
    ]

    # Find atmospheric layer
    layer = layers[0]

    for candidate in layers:
        if h >= candidate[0]:
            layer = candidate
        else:
            break

    h0, T0, P0, lapse = layer

    dh = h - h0

    # Isothermal layer
    if lapse == 0:

        T = T0

        P = P0 * math.exp(
            -G0 * dh /
            (R_AIR * T0)
        )

    else:

        T = T0 + lapse * dh

        P = P0 * (
            T / T0
        ) ** (
            -G0 /
            (R_AIR * lapse)
        )

    rho = P / (R_AIR * T)

    return T, P, rho


# ============================================================
# U.S. Standard Atmosphere density data
#
# density in kg/m^3
#
# Lower-atmosphere points + representative upper-atmosphere
# values from the U.S. Standard Atmosphere 1976.
# ============================================================

ATMOSPHERE_DATA = [

    # altitude km, density kg/m^3

    (0,      1.2250),
    (5,      0.7364),
    (10,     0.4135),
    (15,     0.1948),
    (20,     0.08891),
    (25,     0.04008),
    (30,     0.01841),
    (40,     0.003996),
    (50,     0.001027),
    (60,     0.0003097),
    (70,     8.283e-5),
    (80,     1.846e-5),
    (86,     6.96e-6),

    # upper atmosphere

    (100,    5.604e-7),
    (120,    2.222e-8),
    (140,    3.831e-9),
    (160,    1.233e-9),
    (180,    5.194e-10),
    (200,    2.541e-10),

    (300,    1.916e-11),
    (400,    2.803e-12),
    (500,    5.215e-13),
    (600,    1.137e-13),
    (800,    1.136e-14),
    (1000,   3.561e-15)
]


# ============================================================
# Atmospheric density interpolation
# ============================================================

def air_density(altitude_km):

    if altitude_km <= 0:
        return ATMOSPHERE_DATA[0][1]

    if altitude_km >= ATMOSPHERE_DATA[-1][0]:
        return ATMOSPHERE_DATA[-1][1]

    altitudes = [row[0] for row in ATMOSPHERE_DATA]

    index = bisect.bisect_left(
        altitudes,
        altitude_km
    )

    h1, rho1 = ATMOSPHERE_DATA[index - 1]
    h2, rho2 = ATMOSPHERE_DATA[index]

    # --------------------------------------------------------
    # Logarithmic interpolation
    #
    # Density varies approximately exponentially, so
    # interpolating log(density) is much better than linear.
    # --------------------------------------------------------

    fraction = (
        (altitude_km - h1)
        /
        (h2 - h1)
    )

    log_rho1 = math.log(rho1)
    log_rho2 = math.log(rho2)

    log_density = (
        log_rho1
        +
        fraction * (log_rho2 - log_rho1)
    )

    return math.exp(log_density)


# ============================================================
# Visual atmosphere
# ============================================================

particles = []

NUM_PARTICLES = 25000


def visual_density_probability(altitude):

    rho = air_density(altitude)

    sea_level_density = air_density(0)

    # --------------------------------------------------------
    # Convert physical density to logarithmic visual strength.
    #
    # Sea level:
    #     visual = 1
    #
    # Very thin atmosphere:
    #     still visible
    # --------------------------------------------------------

    min_density = air_density(1000)

    log_rho = math.log10(rho)

    log_min = math.log10(min_density)
    log_max = math.log10(sea_level_density)

    normalized = (
        (log_rho - log_min)
        /
        (log_max - log_min)
    )

    # Adjust visual contrast
    normalized = max(0.0, min(1.0, normalized))

    return normalized ** 2.0


# ============================================================
# Generate atmosphere particles
# ============================================================

def generate_atmosphere():

    particles.clear()

    while len(particles) < NUM_PARTICLES:

        altitude = random.uniform(
            0,
            ATMOSPHERE_HEIGHT
        )

        probability = visual_density_probability(
            altitude
        )

        if random.random() > probability:
            continue

        # Upper semicircle
        angle = random.uniform(
            math.pi,
            2 * math.pi
        )

        radius = (
            EARTH_RADIUS
            +
            altitude
        )

        world_x = (
            radius
            *
            math.cos(angle)
        )

        world_y = (
            radius
            *
            math.sin(angle)
        )

        particles.append(
            (
                world_x,
                world_y,
                altitude
            )
        )


generate_atmosphere()


# ============================================================
# Altitude ruler
# ============================================================

def nice_tick_spacing(zoom):
    """
    Choose a nice altitude interval based on current zoom.

    We try to keep major ticks roughly 80 pixels apart.
    """

    target_pixels = 80

    # How many km would produce ~80 pixels?
    target_km = target_pixels / zoom

    if target_km <= 0:
        return 1

    magnitude = 10 ** math.floor(math.log10(target_km))

    normalized = target_km / magnitude

    if normalized < 1.5:
        nice = 1
    elif normalized < 3:
        nice = 2
    elif normalized < 7:
        nice = 5
    else:
        nice = 10

    return nice * magnitude


def draw_altitude_ruler(
    screen,
    earth_center_x,
    earth_center_y,
    zoom
):
    # --------------------------------------------
    # Surface position
    # --------------------------------------------

    surface_y = earth_center_y - EARTH_RADIUS * zoom

    ruler_x = int(earth_center_x)

    # Don't draw if Earth's top is below the screen
    if surface_y > HEIGHT:
        return

    # --------------------------------------------
    # Determine visible altitude
    # --------------------------------------------

    # Altitude corresponding to top of screen
    max_visible_altitude = (
        (surface_y - 0) / zoom
    )

    max_visible_altitude = max(
        0,
        max_visible_altitude
    )

    # Don't exceed simulated atmosphere
    max_altitude = min(
        max_visible_altitude,
        ATMOSPHERE_HEIGHT
    )

    # --------------------------------------------
    # Dynamic tick interval
    # --------------------------------------------

    major_spacing = nice_tick_spacing(zoom)

    minor_spacing = major_spacing / 5

    # --------------------------------------------
    # Main ruler line
    # --------------------------------------------

    top_y = int(
        surface_y
        -
        max_altitude * zoom
    )

    pygame.draw.line(
        screen,
        (220, 220, 220),
        (ruler_x, int(surface_y)),
        (ruler_x, top_y),
        2
    )

    # --------------------------------------------
    # Minor ticks
    # --------------------------------------------

    altitude = 0

    while altitude <= max_altitude:

        y = int(
            surface_y
            -
            altitude * zoom
        )

        # Major tick?
        major_index = altitude / major_spacing

        is_major = abs(
            major_index - round(major_index)
        ) < 0.0001

        if is_major:

            tick_length = 14

            pygame.draw.line(
                screen,
                (255, 255, 255),
                (ruler_x - tick_length, y),
                (ruler_x + tick_length, y),
                2
            )

            # Altitude label
            label = font.render(
                f"{altitude:g} km",
                True,
                (255, 255, 255)
            )

            screen.blit(
                label,
                (
                    ruler_x + 20,
                    y - label.get_height() // 2
                )
            )

        else:

            tick_length = 7

            pygame.draw.line(
                screen,
                (150, 150, 150),
                (ruler_x - tick_length, y),
                (ruler_x + tick_length, y),
                1
            )

        altitude += minor_spacing


# ============================================================
# Hydrogen Balloon
# ============================================================

class HydrogenBalloon:

    def __init__(self):

        self.altitude = BALLOON_START_ALTITUDE * 1000.0
        self.velocity = 0.0

        self.payload_mass = BALLOON_PAYLOAD_MASS
        self.envelope_mass = BALLOON_ENVELOPE_MASS

        self.cd = BALLOON_CD

        self.burst = False

        # ----------------------------------------------------
        # Initial atmosphere
        # ----------------------------------------------------

        T, P, rho = atmosphere(
            self.altitude / 1000.0
        )

        # ----------------------------------------------------
        # Launch balloon volume
        # ----------------------------------------------------

        launch_radius = BALLOON_LAUNCH_DIAMETER / 2.0

        self.launch_volume = (
            4.0 / 3.0
            * math.pi
            * launch_radius ** 3
        )

        # ----------------------------------------------------
        # Determine hydrogen mass from launch volume
        #
        # PV = mRT
        #
        # m = PV / RT
        # ----------------------------------------------------

        self.hydrogen_mass = (
            P * self.launch_volume
            /
            (R_HYDROGEN * T)
        )

        # ----------------------------------------------------
        # Burst volume
        # ----------------------------------------------------

        burst_radius = BALLOON_BURST_DIAMETER / 2.0

        self.max_volume = (
            4.0 / 3.0
            * math.pi
            * burst_radius ** 3
        )


    # ========================================================
    # Gravity
    # ========================================================

    def gravity(self):

        altitude = self.altitude

        earth_radius_m = EARTH_RADIUS * 1000.0

        return G0 * (
            earth_radius_m /
            (earth_radius_m + altitude)
        ) ** 2


    # ========================================================
    # Balloon geometry
    # ========================================================

    def geometry(self):

        T, P, rho_air = atmosphere(
            self.altitude / 1000.0
        )

        # ----------------------------------------------------
        # Hydrogen expands as pressure decreases
        #
        # V = mRT/P
        # ----------------------------------------------------

        volume = (
            self.hydrogen_mass
            * R_HYDROGEN
            * T
            /
            P
        )

        if volume >= self.max_volume:

            volume = self.max_volume

            self.burst = True

        radius = (
            3.0 * volume
            /
            (4.0 * math.pi)
        ) ** (1.0 / 3.0)

        area = math.pi * radius ** 2

        return volume, radius, area, rho_air, T, P


    # ========================================================
    # Physics timestep
    # ========================================================

    def update(self, dt):

        volume, radius, area, rho_air, T, P = self.geometry()

        g = self.gravity()

        # ----------------------------------------------------
        # Balloon total physical mass
        # ----------------------------------------------------

        physical_mass = (
            self.payload_mass
            + self.envelope_mass
            + self.hydrogen_mass
        )

        # ----------------------------------------------------
        # Buoyancy
        # ----------------------------------------------------

        buoyancy = (
            rho_air
            * volume
            * g
        )

        # ----------------------------------------------------
        # Gravity
        # ----------------------------------------------------

        weight = physical_mass * g

        # ----------------------------------------------------
        # Aerodynamic drag
        #
        # v * |v| automatically gives drag the
        # opposite sign from velocity.
        # ----------------------------------------------------

        drag = (
            0.5
            * rho_air
            * self.cd
            * area
            * self.velocity
            * abs(self.velocity)
        )

        # ----------------------------------------------------
        # Added / virtual air mass
        #
        # Balloon must accelerate some surrounding air.
        # ----------------------------------------------------

        virtual_mass = (
            BALLOON_VIRTUAL_MASS_COEFF
            * rho_air
            * volume
        )

        effective_mass = (
            physical_mass
            + virtual_mass
        )

        # ----------------------------------------------------
        # Net vertical force
        # ----------------------------------------------------

        force = (
            buoyancy
            - weight
            - drag
        )

        acceleration = (
            force
            /
            effective_mass
        )

        # ----------------------------------------------------
        # Integrate
        # ----------------------------------------------------

        self.velocity += acceleration * dt

        self.altitude += self.velocity * dt

        # Don't go below ground
        if self.altitude < 0:

            self.altitude = 0

            if self.velocity < 0:
                self.velocity = 0


    # ========================================================
    # Information
    # ========================================================

    def get_data(self):

        volume, radius, area, rho_air, T, P = self.geometry()

        return {

            "altitude_km":
                self.altitude / 1000.0,

            "velocity":
                self.velocity,

            "diameter":
                radius * 2,

            "volume":
                volume,

            "density":
                rho_air,

            "temperature":
                T,

            "pressure":
                P,

            "burst":
                self.burst
        }

balloon = HydrogenBalloon()
simulation_time = 0.0

# ============================================================
# Main loop
# ============================================================

running = True

while running:

    # --------------------------------------------------------
    # Input
    # --------------------------------------------------------

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

        # ----------------------------------------------------
        # Zoom
        # ----------------------------------------------------

        if event.type == pygame.MOUSEWHEEL:

            mouse_x, mouse_y = pygame.mouse.get_pos()

            old_zoom = zoom

            # Change zoom
            if event.y > 0:
                zoom *= 1.15

            elif event.y < 0:
                zoom /= 1.15

            # Clamp zoom
            zoom = max(
                MIN_ZOOM,
                min(MAX_ZOOM, zoom)
            )

            # --------------------------------------------------
            # Keep the world position under the mouse stationary
            # --------------------------------------------------

            # Earth center BEFORE zoom
            old_center_x = WIDTH // 2 + camera_x
            old_center_y = HEIGHT + camera_y

            # Find the world coordinate currently under mouse
            world_x = (
                mouse_x - old_center_x
            ) / old_zoom

            world_y = (
                mouse_y - old_center_y
            ) / old_zoom

            # Where that same world point would appear after zoom
            new_screen_x = (
                old_center_x
                + world_x * zoom
            )

            new_screen_y = (
                old_center_y
                + world_y * zoom
            )

            # Shift camera so that point stays under cursor
            camera_x += (
                mouse_x - new_screen_x
            )

            camera_y += (
                mouse_y - new_screen_y
            )

        # ----------------------------------------------------
        # Middle mouse pan
        # ----------------------------------------------------

        if event.type == pygame.MOUSEBUTTONDOWN:

            if event.button == 2:

                current_time = pygame.time.get_ticks()

                # Check for double click
                if current_time - last_middle_click <= DOUBLE_CLICK_TIME:

                    # Reset camera
                    zoom = DEFAULT_ZOOM
                    camera_x = 0
                    camera_y = 0

                    # Prevent this click from being reused
                    last_middle_click = 0

                else:

                    last_middle_click = current_time
                    dragging = True

        if event.type == pygame.MOUSEBUTTONUP:

            if event.button == 2:
                dragging = False

        if (
            event.type == pygame.MOUSEMOTION
            and dragging
        ):

            dx, dy = event.rel

            camera_x += dx
            camera_y += dy

    # ============================================================
    # Balloon physics
    # ============================================================

    real_dt = clock.get_time() / 1000.0

    simulation_dt = real_dt * SIMULATION_SPEED

    # Break long frames into small physics steps
    # so the simulation stays stable.

    MAX_PHYSICS_STEP = 0.05

    remaining = simulation_dt

    while remaining > 0:

        dt = min(
            MAX_PHYSICS_STEP,
            remaining
        )

        balloon.update(dt)

        simulation_time += dt

        remaining -= dt

    # ========================================================
    # Draw
    # ========================================================

    screen.fill(SPACE)

    earth_center_x = (
        WIDTH // 2
        +
        camera_x
    )

    earth_center_y = (
        HEIGHT
        +
        camera_y
    )


    # ========================================================
    # Draw atmosphere particles
    # ========================================================

    for world_x, world_y, altitude in particles:

        screen_x = int(
            earth_center_x
            +
            world_x * zoom
        )

        screen_y = int(
            earth_center_y
            +
            world_y * zoom
        )

        if (
            0 <= screen_x < WIDTH
            and
            0 <= screen_y < HEIGHT
        ):

            # ------------------------------------------------
            # Slightly larger particles when zoomed in
            # ------------------------------------------------

            if zoom > 0.5:
                particle_size = 2
            else:
                particle_size = 1

            pygame.draw.circle(
                screen,
                ATMOSPHERE,
                (
                    screen_x,
                    screen_y
                ),
                particle_size
            )


    # ========================================================
    # Draw Earth
    # ========================================================

    radius_pixels = int(
        EARTH_RADIUS * zoom
    )

    pygame.draw.circle(
        screen,
        EARTH,
        (
            earth_center_x,
            earth_center_y
        ),
        radius_pixels
    )


    # ========================================================
    # Draw altitude ruler
    # ========================================================

    draw_altitude_ruler(
        screen,
        earth_center_x,
        earth_center_y,
        zoom
    )

    # ============================================================
    # Draw balloon
    # ============================================================

    data = balloon.get_data()

    balloon_altitude_km = data["altitude_km"]

    # Balloon is directly above top center of Earth
    balloon_world_x = 0

    balloon_world_y = -(
        EARTH_RADIUS
        +
        balloon_altitude_km
    )

    balloon_screen_x = int(
        earth_center_x
        +
        balloon_world_x * zoom
    )

    balloon_screen_y = int(
        earth_center_y
        +
        balloon_world_y * zoom
    )

    # ------------------------------------------------------------
    # Visual balloon size
    #
    # Actual balloon diameter is meters, while world coordinates
    # are kilometers.
    # ------------------------------------------------------------

    balloon_radius_km = (
        data["diameter"]
        /
        2
        /
        1000
    )

    balloon_radius_pixels = int(
        balloon_radius_km
        * zoom
    )

    # Real balloon becomes too small to see when zoomed far out,
    # so enforce a minimum display size.
    balloon_radius_pixels = max(
        5,
        balloon_radius_pixels
    )

    pygame.draw.circle(
        screen,
        (255, 230, 50),
        (
            balloon_screen_x,
            balloon_screen_y
        ),
        balloon_radius_pixels
    )

    # ============================================================
    # Balloon information
    # ============================================================

    data = balloon.get_data()

    info_lines = [

        f"Time: {simulation_time:.1f} s",

        f"Altitude: {data['altitude_km']:.2f} km",

        f"Vertical speed: {data['velocity']:.2f} m/s",

        f"Balloon diameter: {data['diameter']:.2f} m",

        f"Volume: {data['volume']:.1f} m³",

        f"Air density: {data['density']:.6f} kg/m³",

        f"Pressure: {data['pressure'] / 1000:.2f} kPa",

        f"Temperature: {data['temperature'] - 273.15:.1f} °C"
    ]

    for i, line in enumerate(info_lines):

        text = info_font.render(
            line,
            True,
            (255, 255, 255)
        )

        screen.blit(
            text,
            (
                20,
                20 + i * 25
            )
        )

    pygame.display.flip()

    clock.tick(60)


pygame.quit()
sys.exit()