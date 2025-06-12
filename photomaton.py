#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Photo Booth GUI for Raspberry Pi - 3 Fotos Secuenciales
- Detects coin insertion
- Displays graphical interface on HDMI screen
- Takes 3 photos with USB webcam in sequence
- Prints photos
"""
#TODO: quitar cualquier referencia a Nila del fuente y todos los mensajes en ingles
#TODO: numero fijo de fotos en fichero rotativo
#TODO: transformacion en servicio y carga de settings desde linea de comandos --congig_file=path_to_file
#TODO: Example settings.yml file with all options and possible values

import time
import os
import cv2
import RPi.GPIO as GPIO
import pygame
from datetime import datetime
from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFont
import cups
import numpy as np
import threading
import yaml
import os.path

# Load the YAML settings file
try:
    with open('settings.yml', 'r') as file:
        settings = yaml.safe_load(file)
        print(f"Settings successfully loaded from {file.name}")
        
except Exception as e:
    print(f"Error loading settings file from {file.name}: {e}")
    print("Using default settings.")
    settings = {}
# ------------------------------------------------------
# Settings
# ------------------------------------------------------
SCREEN_TITTLE = settings.get('SCREEN_TITTLE', "3 fotos por 1 euro")
SCREEN_SUBTITLE = settings.get('SCREEN_SUBTITLE', "INSERT COIN")
FRAME_TITTLE = settings.get('FRAME_TITTLE', "<< Fotomatón de Nila >>")

PICTURE_BORDER_SIZE = settings.get('PICTURE_BORDER_SIZE', 50)
PICTURE_BORDER_COLOR = settings.get('PICTURE_BORDER_COLOR', 'white')

BLINK_ENABLED = settings.get('BLINK_ENABLED', True)  # Activar/desactivar efecto intermitente
BLINK_SPEED = settings.get('BLINK_SPEED', 500)     # Velocidad de parpadeo en milisegundos (500 = medio segundo)

# Configuración de tiempos para las 3 fotos
INITIAL_COUNTDOWN_TIME = settings.get('INITIAL_COUNTDOWN_TIME', 5)  # Tiempo inicial antes de la primera foto
BETWEEN_PHOTOS_TIME = settings.get('BETWEEN_PHOTOS_TIME', 2)  # Tiempo entre fotos
TOTAL_PHOTOS = 3  # Número total de fotos a tomar

# Configuración para imagen compuesta
COMPOSITE_SPACING = settings.get('COMPOSITE_SPACING', 20)  # Espacio entre fotos en la imagen compuesta
COMPOSITE_MARGIN = settings.get('COMPOSITE_MARGIN', 40)    # Margen alrededor de la imagen compuesta
COMPOSITE_ADD_HEADER = settings.get('COMPOSITE_ADD_HEADER', True)  # Agregar texto de fecha/hora
COMPOSITE_LAYOUT = settings.get('COMPOSITE_LAYOUT', 'vertical')  # 'vertical' o 'horizontal'

COIN_PIN = settings.get('COIN_PIN', 17)  # El pin GPIO donde está conectado el detector de monedas
LED_PIN = settings.get('LED_PIN', 27)   # Pin para un LED opcional

# Configuración de la pantalla
SCREEN_WIDTH = settings.get('SCREEN_WIDTH', 1280)
SCREEN_HEIGHT = settings.get('SCREEN_HEIGHT', 720)
FULLSCREEN = settings.get('FULLSCREEN', True)  # Cambiar a False para modo ventana durante desarrollo

# Configuración del marco
FRAME_ENABLED = settings.get('FRAME_ENABLED', True)
FRAME_THICKNESS = settings.get('FRAME_THICKNESS', 60)  # Grosor del marco en píxeles
FRAME_COLOR = settings.get('FRAME_COLOR', (50, 50, 50))  # Color del marco (gris oscuro)
FRAME_INNER_COLOR = settings.get('FRAME_INNER_COLOR', (20, 20, 20))  # Color del borde interior (casi negro)
FRAME_INNER_THICKNESS = settings.get('FRAME_INNER_THICKNESS', 5)  # Grosor del borde interior
FRAME_ROUNDED = settings.get('FRAME_ROUNDED', True)  # Si quieres que el marco tenga esquinas redondeadas
FRAME_CORNER_RADIUS = settings.get('FRAME_CORNER_RADIUS', 20)  # Radio de las esquinas redondeadas (si FRAME_ROUNDED es True)

# Configuración de colores
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)

# Ruta a la carpeta de fuentes
FONT_DIR = os.path.join(os.path.expanduser('./'), 'fonts')
# Nombre del archivo de fuente retro (cambiar según la fuente descargada)
RETRO_FONT = "PressStart2P-Regular.ttf"  # O la fuente que hayas descargado
# Ruta completa a la fuente
RETRO_FONT_PATH = os.path.join(FONT_DIR, RETRO_FONT)

# Usar fuente alternativa si la principal no está disponible
USE_FALLBACK_FONT = True  # Cambiar a False para usar solo fuentes de sistema si la retro falla

# Configuración de directorios
SAVE_DIR = os.path.join(os.path.expanduser('~'), 'photobooth_images')
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

class PhotoboothGUI:
    def __init__(self):
        # Inicializar GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(COIN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(LED_PIN, GPIO.OUT)
        GPIO.output(LED_PIN, GPIO.LOW)
        
        # Inicializar Pygame
        pygame.init()
        pygame.mouse.set_visible(False)  # Ocultar el cursor
        
        if FULLSCREEN:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            
        pygame.display.set_caption("Raspberry Pi Photobooth")
        
        # Cargar fuentes
        self.font_large = pygame.font.Font(None, 80)
        self.font_medium = pygame.font.Font(None, 60)
        self.font_small = pygame.font.Font(None, 40)

        try:
            # Intentar cargar la fuente retro
            if os.path.exists(RETRO_FONT_PATH):
                self.font_large = pygame.font.Font(RETRO_FONT_PATH, 60)
                self.font_medium = pygame.font.Font(RETRO_FONT_PATH, 40)
                self.font_small = pygame.font.Font(RETRO_FONT_PATH, 30)
                print(f"Fuente retro '{RETRO_FONT}' cargada con éxito")
            else:
                # Si no se encuentra el archivo, usar fuentes alternativas
                if USE_FALLBACK_FONT:
                    # Intentar cargar una fuente de sistema de aspecto retro
                    retro_system_fonts = ['monospace', 'courier', 'fixedsys', 'consolas']
                    font_loaded = False
                    
                    for font_name in retro_system_fonts:
                        if font_name in pygame.font.get_fonts():
                            self.font_large = pygame.font.SysFont(font_name, 70, bold=True)
                            self.font_medium = pygame.font.SysFont(font_name, 50, bold=True)
                            self.font_small = pygame.font.SysFont(font_name, 35, bold=True)
                            print(f"Usando fuente de sistema '{font_name}' como alternativa")
                            font_loaded = True
                            break
                    
                    if not font_loaded:
                        # Si ninguna de las alternativas está disponible, usar la fuente predeterminada
                        self.font_large = pygame.font.Font(None, 80)
                        self.font_medium = pygame.font.Font(None, 60)
                        self.font_small = pygame.font.Font(None, 40)
                        print("No se encontraron fuentes retro, usando fuente predeterminada")
                else:
                    # Usar las fuentes predeterminadas si no se usa respaldo
                    self.font_large = pygame.font.Font(None, 80)
                    self.font_medium = pygame.font.Font(None, 60)
                    self.font_small = pygame.font.Font(None, 40)
                    print(f"Fuente retro no encontrada en '{RETRO_FONT_PATH}'. Usando fuente predeterminada")
        except Exception as e:
            # En caso de error, volver a las fuentes predeterminadas
            self.font_large = pygame.font.Font(None, 80)
            self.font_medium = pygame.font.Font(None, 60)
            self.font_small = pygame.font.Font(None, 40)
            print(f"Error al cargar la fuente retro: {e}. Usando fuente predeterminada")
        
        # Inicializar cámara
        self.camera = None
        self.connect_camera()
        
        # Variables de estado para secuencia de 3 fotos
        self.running = True
        self.current_state = "waiting_coin"  # Estados: waiting_coin, initial_countdown, taking_photos, show_photos
        self.countdown_value = INITIAL_COUNTDOWN_TIME
        self.photos_taken = 0  # Contador de fotos tomadas
        self.current_photo_countdown = 0  # Cuenta regresiva entre fotos
        self.taken_photos = []  # Lista para almacenar las fotos tomadas
        self.session_timestamp = None  # Timestamp de la sesión actual

        # Para el efecto de parpadeo
        self.blink_visible = True
        self.last_blink_time = pygame.time.get_ticks()
        
        # Configuración de impresora
        self.printer_name = None
        try:
            self.conn = cups.Connection()
            self.printers = self.conn.getPrinters()
            
            # Si hay impresoras disponibles, usar la primera
            if self.printers:
                self.printer_name = list(self.printers.keys())[0]
                print(f"Impresora encontrada: {self.printer_name}")
            else:
                print("No se encontraron impresoras. Las fotos se guardarán pero no se imprimirán.")
        except Exception as e:
            print(f"Error al conectar con CUPS: {e}")
            print("El sistema de impresión no está disponible. Las fotos se guardarán pero no se imprimirán.")
            self.conn = None
        
        # Crear un thread para la detección de monedas
        self.coin_thread = threading.Thread(target=self.coin_detection_loop)
        self.coin_thread.daemon = True
        self.coin_thread.start()
    
    def draw_frame(self):
        """Dibuja un marco decorativo alrededor de la pantalla."""
        if not FRAME_ENABLED:
            return
        
        # Área interior del marco (el espacio donde se muestra el contenido)
        interior_rect = pygame.Rect(
            FRAME_THICKNESS, 
            FRAME_THICKNESS, 
            SCREEN_WIDTH - 2 * FRAME_THICKNESS, 
            SCREEN_HEIGHT - 2 * FRAME_THICKNESS
        )
        
        # Dibuja el marco exterior (cubre toda la pantalla)
        if FRAME_ROUNDED:
            # Para marco con esquinas redondeadas, dibujamos rectángulos y círculos
            # Marco superior
            pygame.draw.rect(self.screen, FRAME_COLOR, 
                            (FRAME_CORNER_RADIUS, 0, 
                            SCREEN_WIDTH - 2 * FRAME_CORNER_RADIUS, FRAME_THICKNESS))
            # Marco inferior
            pygame.draw.rect(self.screen, FRAME_COLOR, 
                            (FRAME_CORNER_RADIUS, SCREEN_HEIGHT - FRAME_THICKNESS, 
                            SCREEN_WIDTH - 2 * FRAME_CORNER_RADIUS, FRAME_THICKNESS))
            # Marco izquierdo
            pygame.draw.rect(self.screen, FRAME_COLOR, 
                            (0, FRAME_CORNER_RADIUS, 
                            FRAME_THICKNESS, SCREEN_HEIGHT - 2 * FRAME_CORNER_RADIUS))
            # Marco derecho
            pygame.draw.rect(self.screen, FRAME_COLOR, 
                            (SCREEN_WIDTH - FRAME_THICKNESS, FRAME_CORNER_RADIUS, 
                            FRAME_THICKNESS, SCREEN_HEIGHT - 2 * FRAME_CORNER_RADIUS))
            
            # Esquinas redondeadas (círculos en las 4 esquinas)
            # Esquina superior izquierda
            pygame.draw.circle(self.screen, FRAME_COLOR, 
                            (FRAME_CORNER_RADIUS, FRAME_CORNER_RADIUS), FRAME_CORNER_RADIUS)
            # Esquina superior derecha
            pygame.draw.circle(self.screen, FRAME_COLOR, 
                            (SCREEN_WIDTH - FRAME_CORNER_RADIUS, FRAME_CORNER_RADIUS), FRAME_CORNER_RADIUS)
            # Esquina inferior izquierda
            pygame.draw.circle(self.screen, FRAME_COLOR, 
                            (FRAME_CORNER_RADIUS, SCREEN_HEIGHT - FRAME_CORNER_RADIUS), FRAME_CORNER_RADIUS)
            # Esquina inferior derecha
            pygame.draw.circle(self.screen, FRAME_COLOR, 
                            (SCREEN_WIDTH - FRAME_CORNER_RADIUS, SCREEN_HEIGHT - FRAME_CORNER_RADIUS), FRAME_CORNER_RADIUS)
        else:
            # Marco simple sin esquinas redondeadas
            pygame.draw.rect(self.screen, FRAME_COLOR, (0, 0, SCREEN_WIDTH, FRAME_THICKNESS))  # Superior
            pygame.draw.rect(self.screen, FRAME_COLOR, (0, SCREEN_HEIGHT - FRAME_THICKNESS, SCREEN_WIDTH, FRAME_THICKNESS))  # Inferior
            pygame.draw.rect(self.screen, FRAME_COLOR, (0, 0, FRAME_THICKNESS, SCREEN_HEIGHT))  # Izquierdo
            pygame.draw.rect(self.screen, FRAME_COLOR, (SCREEN_WIDTH - FRAME_THICKNESS, 0, FRAME_THICKNESS, SCREEN_HEIGHT))  # Derecho
        
        # Dibuja el borde interior (para dar efecto de profundidad)
        # Esto crea una línea fina alrededor del área interior
        pygame.draw.rect(self.screen, FRAME_INNER_COLOR, interior_rect, FRAME_INNER_THICKNESS)
                        
        # Añadir decoración al marco - texto en la parte superior
        logo_text = self.font_small.render(FRAME_TITTLE, True, WHITE)
        self.screen.blit(logo_text, (SCREEN_WIDTH//2 - logo_text.get_width()//2, FRAME_THICKNESS//2 - logo_text.get_height()//2))
    
    def connect_camera(self):
        """Conecta a la webcam."""
        try:
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                print("Error: No se pudo abrir la cámara.")
                return False
            
            # Configurar resolución
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, SCREEN_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, SCREEN_HEIGHT)
            print("Cámara conectada con éxito.")
            return True
        except Exception as e:
            print(f"Error al conectar la cámara: {e}")
            return False
    
    def get_camera_frame(self):
        """Obtiene un frame de la cámara y lo convierte a formato Pygame con efecto espejo."""
        if self.camera is None or not self.camera.isOpened():
            return None
        
        ret, frame = self.camera.read()
        if not ret:
            return None
        
        # Invertir horizontalmente la imagen para efecto espejo en la vista previa
        frame = cv2.flip(frame, 1)  # 1 = voltear horizontalmente, 0 = voltear verticalmente
        
        # Convertir de OpenCV (BGR) a Pygame (RGB)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = np.rot90(frame)  # Rotar si es necesario
        frame = pygame.surfarray.make_surface(frame)
        return frame
    
    def take_photo(self):
        """Toma una foto con la webcam."""
        if self.camera is None or not self.camera.isOpened():
            print("La cámara no está disponible.")
            return None
        
        # Capturar imagen
        ret, frame = self.camera.read()
        if not ret:
            print("Error al capturar la imagen.")
            return None
        
        # Generar nombre de archivo con timestamp de la sesión y número de foto
        if self.session_timestamp is None:
            self.session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        filename = f"photobooth_{self.session_timestamp}_foto{self.photos_taken + 1}.jpg"
        filepath = os.path.join(SAVE_DIR, filename)
        
        # Guardar imagen original
        cv2.imwrite(filepath, frame)
        
        # Mejorar y aplicar filtros a la imagen con PIL
        image = Image.open(filepath)
        
        # Ajustes básicos: brillo, contraste y saturación
        image = ImageEnhance.Brightness(image).enhance(1.2)
        image = ImageEnhance.Contrast(image).enhance(1.1)
        image = ImageEnhance.Color(image).enhance(1.2)
        
        # Añadir un borde 
        image = ImageOps.expand(image, border=PICTURE_BORDER_SIZE, fill=PICTURE_BORDER_COLOR)
        
        # Guardar imagen modificada
        image.save(filepath)
        print(f"Foto {self.photos_taken + 1} guardada como {filepath}")
        
        # Convertir la imagen para mostrarla en pygame
        pygame_image = pygame.image.load(filepath)
        pygame_image = pygame.transform.scale(pygame_image, (SCREEN_WIDTH, SCREEN_HEIGHT))
        
        # Agregar a la lista de fotos tomadas
        self.taken_photos.append(pygame_image)
        self.photos_taken += 1
        
        return filepath
    
    def create_composite_image(self):
        """Crea una imagen compuesta con las 3 fotos en una sola hoja."""
        try:
            # Cargar las 3 imágenes individuales
            images = []
            for i in range(TOTAL_PHOTOS):
                photo_path = f"photobooth_{self.session_timestamp}_foto{i+1}.jpg"
                full_path = os.path.join(SAVE_DIR, photo_path)
                if os.path.exists(full_path):
                    img = Image.open(full_path)
                    images.append(img)
                else:
                    print(f"No se encontró la imagen: {full_path}")
                    return None
            
            if len(images) != TOTAL_PHOTOS:
                print("No se pudieron cargar todas las imágenes")
                return None
            
            # Obtener dimensiones de las imágenes (asumiendo que todas son iguales)
            img_width, img_height = images[0].size
            
            # Configuración para la disposición
            spacing = COMPOSITE_SPACING
            margin = COMPOSITE_MARGIN
            header_height = 50 if COMPOSITE_ADD_HEADER else 0
            
            # Calcular dimensiones según el layout
            if COMPOSITE_LAYOUT == 'horizontal':
                # 3 fotos horizontalmente
                composite_width = (img_width * TOTAL_PHOTOS) + (spacing * (TOTAL_PHOTOS - 1)) + 2 * margin
                composite_height = img_height + 2 * margin + header_height
            else:
                # 3 fotos verticalmente (por defecto)
                composite_width = img_width + 2 * margin
                composite_height = (img_height * TOTAL_PHOTOS) + (spacing * (TOTAL_PHOTOS - 1)) + 2 * margin + header_height
            
            # Crear imagen compuesta con fondo blanco
            composite = Image.new('RGB', (composite_width, composite_height), 'white')
            
            # Agregar texto en la parte superior (si está habilitado)
            text_height_used = 0
            if COMPOSITE_ADD_HEADER:
                try:
                    draw = ImageDraw.Draw(composite)
                    
                    # Intentar usar una fuente del sistema
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
                    except:
                        try:
                            font = ImageFont.truetype("arial.ttf", 24)
                        except:
                            font = ImageFont.load_default()
                    
                    # Texto en la parte superior
                    header_text = f"Fotomatón - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    text_bbox = draw.textbbox((0, 0), header_text, font=font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_x = (composite_width - text_width) // 2
                    
                    draw.text((text_x, 10), header_text, fill='black', font=font)
                    text_height_used = header_height
                    
                except Exception as e:
                    print(f"No se pudo agregar texto al compuesto: {e}")
                    text_height_used = 0
            
            # Colocar las fotos según el layout
            if COMPOSITE_LAYOUT == 'horizontal':
                # Disposición horizontal
                x_position = margin
                y_position = margin + text_height_used
                for i, img in enumerate(images):
                    composite.paste(img, (x_position, y_position))
                    x_position += img_width + spacing
            else:
                # Disposición vertical (por defecto)
                x_position = margin
                y_position = margin + text_height_used
                for i, img in enumerate(images):
                    composite.paste(img, (x_position, y_position))
                    y_position += img_height + spacing
            
            # Guardar la imagen compuesta
            composite_filename = f"photobooth_{self.session_timestamp}_compuesta.jpg"
            composite_path = os.path.join(SAVE_DIR, composite_filename)
            composite.save(composite_path, 'JPEG', quality=95)
            
            print(f"Imagen compuesta creada: {composite_path}")
            print(f"Dimensiones: {composite_width}x{composite_height} - Layout: {COMPOSITE_LAYOUT}")
            return composite_path
            
        except Exception as e:
            print(f"Error al crear imagen compuesta: {e}")
            return None

    def print_photos(self):
        """Crea una imagen compuesta y la envía a la impresora."""
        if not self.printer_name or not self.conn:
            print("Sistema de impresión no disponible. Las fotos se guardarán sin imprimir.")
            return False
        
        def print_composite():
            try:
                # Crear imagen compuesta
                composite_path = self.create_composite_image()
                if composite_path and os.path.exists(composite_path):
                    print(f"Imprimiendo imagen compuesta: {composite_path}")
                    job_id = self.conn.printFile(
                        self.printer_name, 
                        composite_path, 
                        "Photobooth Composite", 
                        {}
                    )
                    print(f"Trabajo de impresión enviado. ID: {job_id}")
                else:
                    print("No se pudo crear la imagen compuesta para imprimir")
            except Exception as e:
                print(f"Error al imprimir imagen compuesta: {e}")
        
        # Iniciar la impresión en un hilo separado para no bloquear la interfaz
        print_thread = threading.Thread(target=print_composite)
        print_thread.daemon = True
        print_thread.start()
    
    def coin_detection_loop(self):
        """Bucle de detección de monedas en un hilo separado."""
        while self.running:
            if self.current_state == "waiting_coin" and GPIO.input(COIN_PIN) == GPIO.HIGH:
                print("¡Moneda detectada! Iniciando secuencia de 3 fotos...")
                GPIO.output(LED_PIN, GPIO.HIGH)  # Encender LED
                self.start_photo_sequence()
                # Esperar un momento para evitar rebotes
                time.sleep(0.2)
                GPIO.output(LED_PIN, GPIO.LOW)  # Apagar LED
            time.sleep(0.1)  # Pequeña pausa para no saturar la CPU
    
    def start_photo_sequence(self):
        """Inicia la secuencia de 3 fotos."""
        self.current_state = "initial_countdown"
        self.countdown_value = INITIAL_COUNTDOWN_TIME
        self.photos_taken = 0
        self.taken_photos = []
        self.session_timestamp = None
        self.current_photo_countdown = 0
    
    def draw_waiting_screen(self):
        """Dibuja la pantalla de espera de moneda."""
        self.screen.fill(BLACK)
        
        # Mostrar vista previa de la cámara
        camera_frame = self.get_camera_frame()
        if camera_frame:
            # Hacer la imagen más oscura para que el texto sea visible
            dark_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            dark_overlay.fill((0, 0, 0, 128))  # Negro semi-transparente
            
            self.screen.blit(camera_frame, (0, 0))
            self.screen.blit(dark_overlay, (0, 0))
        
        # Texto principal
        text1 = self.font_large.render(SCREEN_TITTLE, True, WHITE)
        text2 = self.font_medium.render(SCREEN_SUBTITLE, True, WHITE)
        
        # Centrar texto
        text1_rect = text1.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 50))
        text2_rect = text2.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 50))
        
        # Dibujar texto con un resplandor
        for offset in range(1, 5, 2):
            glow_rect = text1_rect.copy()
            glow_rect.x += offset
            glow_rect.y += offset
            text_glow = self.font_large.render(SCREEN_TITTLE, True, BLUE)
            self.screen.blit(text_glow, glow_rect)
        
        self.screen.blit(text1, text1_rect)
         # Controlar la intermitencia del texto secundario
        current_time = pygame.time.get_ticks()
        if current_time - self.last_blink_time >= BLINK_SPEED:
            self.blink_visible = not self.blink_visible
            self.last_blink_time = current_time
        
        # Solo mostrar el texto "Insert coin" si está visible en el ciclo de parpadeo o si el parpadeo está desactivado
        if self.blink_visible or not BLINK_ENABLED:
            text2 = self.font_medium.render(SCREEN_SUBTITLE, True, WHITE)
            text2_rect = text2.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 50))
            self.screen.blit(text2, text2_rect)
            
        # Dibujar el marco por encima de todo
        self.draw_frame()
    
    def draw_initial_countdown_screen(self):
        """Dibuja la pantalla de cuenta regresiva inicial (5 segundos)."""
        self.screen.fill(BLACK)
        
        # Mostrar vista previa de la cámara
        camera_frame = self.get_camera_frame()
        if camera_frame:
            self.screen.blit(camera_frame, (0, 0))
        
        # Círculo de cuenta regresiva
        pygame.draw.circle(self.screen, WHITE, (SCREEN_WIDTH//2, SCREEN_HEIGHT//2), 100, 5)
        
        # Número de cuenta regresiva
        text = self.font_large.render(str(self.countdown_value), True, RED)
        text_rect = text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
        self.screen.blit(text, text_rect)
        
        # Texto preparativo
        if self.countdown_value > INITIAL_COUNTDOWN_TIME / 2:
            prep_text = "¡Prepárate!"
        elif self.countdown_value > INITIAL_COUNTDOWN_TIME / 4:
            prep_text = "SONRÍE!"
        else:
            prep_text = "¡PRIMERA FOTO!"
            
        prep_render = self.font_medium.render(prep_text, True, WHITE)
        prep_rect = prep_render.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 150))
        self.screen.blit(prep_render, prep_rect)
        
        # Información de sesión
        info_text = f"SESIÓN DE 3 FOTOS - FOTO 1/{TOTAL_PHOTOS}"
        info_render = self.font_small.render(info_text, True, YELLOW)
        info_rect = info_render.get_rect(center=(SCREEN_WIDTH//2, 100))
        self.screen.blit(info_render, info_rect)
        
        # Dibujar el marco por encima de todo
        self.draw_frame()
    
    def draw_taking_photos_screen(self):
        """Dibuja la pantalla durante la toma de fotos 2 y 3."""
        self.screen.fill(BLACK)
        
        # Mostrar vista previa de la cámara
        camera_frame = self.get_camera_frame()
        if camera_frame:
            self.screen.blit(camera_frame, (0, 0))
        
        # Círculo de cuenta regresiva más pequeño
        pygame.draw.circle(self.screen, WHITE, (SCREEN_WIDTH//2, SCREEN_HEIGHT//2), 80, 5)
        
        # Número de cuenta regresiva
        text = self.font_large.render(str(self.current_photo_countdown), True, GREEN)
        text_rect = text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
        self.screen.blit(text, text_rect)
        
        # Texto indicativo
        if self.current_photo_countdown > 1:
            prep_text = f"Siguiente foto en..."
        else:
            prep_text = f"¡FOTO {self.photos_taken + 1}!"
            
        prep_render = self.font_medium.render(prep_text, True, WHITE)
        prep_rect = prep_render.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 150))
        self.screen.blit(prep_render, prep_rect)
        
        # Información de progreso
        progress_text = f"FOTO {self.photos_taken + 1}/{TOTAL_PHOTOS}"
        progress_render = self.font_small.render(progress_text, True, YELLOW)
        progress_rect = progress_render.get_rect(center=(SCREEN_WIDTH//2, 100))
        self.screen.blit(progress_render, progress_rect)
        
        # Mostrar miniaturas de fotos ya tomadas en la parte inferior
        if self.taken_photos:
            mini_y = SCREEN_HEIGHT - 150
            mini_width = 120
            mini_height = 80
            spacing = 20
            start_x = SCREEN_WIDTH//2 - (len(self.taken_photos) * (mini_width + spacing) - spacing)//2
            
            for i, photo in enumerate(self.taken_photos):
                mini_photo = pygame.transform.scale(photo, (mini_width, mini_height))
                self.screen.blit(mini_photo, (start_x + i * (mini_width + spacing), mini_y))
                
                # Marco blanco alrededor de la miniatura
                pygame.draw.rect(self.screen, WHITE, 
                               (start_x + i * (mini_width + spacing) - 2, mini_y - 2, 
                                mini_width + 4, mini_height + 4), 2)
        
        # Dibujar el marco por encima de todo
        self.draw_frame()
    
    def draw_show_photos_screen(self):
        """Dibuja la pantalla con las 3 fotos tomadas."""
        self.screen.fill(BLACK)
        
        if len(self.taken_photos) >= 3:
            # Mostrar las 3 fotos en una disposición 1x3 horizontal
            photo_width = SCREEN_WIDTH // 3 - 20
            photo_height = int(photo_width * 0.75)  # Relación de aspecto 4:3
            start_y = (SCREEN_HEIGHT - photo_height) // 2
            
            for i, photo in enumerate(self.taken_photos):
                x_pos = 10 + i * (photo_width + 10)
                scaled_photo = pygame.transform.scale(photo, (photo_width, photo_height))
                self.screen.blit(scaled_photo, (x_pos, start_y))
                
                # Marco blanco alrededor de cada foto
                pygame.draw.rect(self.screen, WHITE, 
                               (x_pos - 2, start_y - 2, photo_width + 4, photo_height + 4), 3)
                
                # Número de foto
                num_text = self.font_small.render(f"{i+1}", True, WHITE)
                self.screen.blit(num_text, (x_pos + 10, start_y + 10))
        
        # Texto indicativo
        if self.printer_name and self.conn:
            text = self.font_medium.render("¡Tus 3 fotos se están imprimiendo en una hoja!", True, GREEN)
        else:
            text = self.font_medium.render("¡Sesión completada! 3 fotos guardadas", True, GREEN)
            
        text_rect = text.get_rect(center=(SCREEN_WIDTH//2, 100))
        
        # Fondo semi-transparente para el texto
        text_bg = pygame.Surface((text_rect.width + 40, text_rect.height + 20), pygame.SRCALPHA)
        text_bg.fill((0, 0, 0, 180))
        self.screen.blit(text_bg, (text_rect.x - 20, text_rect.y - 10))
        self.screen.blit(text, text_rect)
        
        # Mensaje adicional
        thanks_text = self.font_small.render("¡Gracias por usar nuestro fotomatón!", True, WHITE)
        thanks_rect = thanks_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT - 50))
        self.screen.blit(thanks_text, thanks_rect)
        
        # Dibujar el marco por encima de todo
        self.draw_frame()
    
    def update_initial_countdown(self):
        """Actualiza la cuenta regresiva inicial (5 segundos)."""
        if self.current_state == "initial_countdown":
            current_time = pygame.time.get_ticks()
            
            if not hasattr(self, 'last_countdown_time'):
                self.last_countdown_time = current_time
            
            # Actualizar cada segundo
            if current_time - self.last_countdown_time >= 1000:
                self.countdown_value -= 1
                self.last_countdown_time = current_time
                
                # Parpadear LED
                GPIO.output(LED_PIN, GPIO.HIGH)
                pygame.time.delay(100)
                GPIO.output(LED_PIN, GPIO.LOW)
                
                # Si la cuenta llega a cero, tomar primera foto
                if self.countdown_value <= 0:
                    self.take_first_photo()
    
    def take_first_photo(self):
        """Toma la primera foto y configura para las siguientes."""
        # Flash effect
        self.screen.fill(WHITE)
        pygame.display.flip()
        pygame.time.delay(100)
        
        # Tomar primera foto
        filepath = self.take_photo()
        if filepath:
            print("Primera foto tomada!")
            
        # Cambiar al estado de tomar más fotos
        self.current_state = "taking_photos"
        self.current_photo_countdown = BETWEEN_PHOTOS_TIME
        self.last_photo_countdown_time = pygame.time.get_ticks()
    
    def update_photo_sequence(self):
        """Actualiza la secuencia de fotos 2 y 3."""
        if self.current_state == "taking_photos":
            current_time = pygame.time.get_ticks()
            
            # Actualizar cada segundo
            if current_time - self.last_photo_countdown_time >= 1000:
                self.current_photo_countdown -= 1
                self.last_photo_countdown_time = current_time
                
                # Parpadear LED
                GPIO.output(LED_PIN, GPIO.HIGH)
                pygame.time.delay(50)
                GPIO.output(LED_PIN, GPIO.LOW)
                
                # Si la cuenta llega a cero, tomar foto
                if self.current_photo_countdown <= 0:
                    # Flash effect
                    self.screen.fill(WHITE)
                    pygame.display.flip()
                    pygame.time.delay(100)
                    
                    # Tomar foto
                    filepath = self.take_photo()
                    if filepath:
                        print(f"Foto {self.photos_taken} tomada!")
                    
                    # Verificar si ya tomamos las 3 fotos
                    if self.photos_taken >= TOTAL_PHOTOS:
                        # Todas las fotos tomadas, mostrar resultado
                        print("¡Sesión de 3 fotos completada!")
                        self.print_photos()
                        self.current_state = "show_photos"
                        self.photo_display_start = pygame.time.get_ticks()
                    else:
                        # Preparar para la siguiente foto
                        self.current_photo_countdown = BETWEEN_PHOTOS_TIME
    
    def run(self):
        """Bucle principal del programa."""
        clock = pygame.time.Clock()
        
        try:
            while self.running:
                # Manejo de eventos
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self.running = False
                        # Para pruebas: simular inserción de moneda con la tecla espacio
                        elif event.key == pygame.K_SPACE and self.current_state == "waiting_coin":
                            self.start_photo_sequence()
                
                # Actualizar estado
                if self.current_state == "initial_countdown":
                    self.update_initial_countdown()
                elif self.current_state == "taking_photos":
                    self.update_photo_sequence()
                elif self.current_state == "show_photos":
                    # Mostrar las fotos durante X segundos
                    current_time = pygame.time.get_ticks()
                    if not hasattr(self, 'photo_display_start'):
                        self.photo_display_start = current_time
                    
                    if current_time - self.photo_display_start >= 8000:  # 8 segundos para ver las 3 fotos
                        self.current_state = "waiting_coin"
                        delattr(self, 'photo_display_start')
                        # Limpiar variables para la siguiente sesión
                        self.photos_taken = 0
                        self.taken_photos = []
                        self.session_timestamp = None
                
                # Dibujar pantalla según el estado actual
                if self.current_state == "waiting_coin":
                    self.draw_waiting_screen()
                elif self.current_state == "initial_countdown":
                    self.draw_initial_countdown_screen()
                elif self.current_state == "taking_photos":
                    self.draw_taking_photos_screen()
                elif self.current_state == "show_photos":
                    self.draw_show_photos_screen()
                
                pygame.display.flip()
                clock.tick(30)  # 30 FPS
                
        except KeyboardInterrupt:
            print("Programa terminado por el usuario.")
        finally:
            # Limpieza
            self.cleanup()
    
    def cleanup(self):
        """Liberar recursos al cerrar."""
        print("Limpiando recursos...")
        if self.camera is not None and self.camera.isOpened():
            self.camera.release()
        GPIO.cleanup()
        pygame.quit()
        print("Programa finalizado.")

if __name__ == "__main__":
    # Iniciar el fotomatón con GUI
    booth = PhotoboothGUI()
    booth.run()