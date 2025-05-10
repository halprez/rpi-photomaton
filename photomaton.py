#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicación de Fotomatón con Interfaz Gráfica para Raspberry Pi
- Detecta monedas a través del GPIO
- Muestra interfaz gráfica en pantalla HDMI
- Toma fotos con webcam USB
- Imprime las fotos
"""

import time
import os
import cv2
import RPi.GPIO as GPIO
import pygame
from datetime import datetime
from PIL import Image, ImageEnhance, ImageOps
import cups
import numpy as np
import threading
# Borde de foto
PICTURE_BORDER_SIZE = 50
PICTURE_BORDER_COLOR='white'

# Configuración GPIO
COIN_PIN = 17  # El pin GPIO donde está conectado el detector de monedas
LED_PIN = 27   # Pin para un LED opcional

# Configuración de la pantalla
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FULLSCREEN = True  # Cambiar a False para modo ventana durante desarrollo

# Configuración de colores
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

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
        
        # Inicializar cámara
        self.camera = None
        self.connect_camera()
        
        # Variables de estado
        self.running = True
        self.current_state = "waiting_coin"  # Estados: waiting_coin, countdown, show_photo
        self.countdown_value = 5
        self.last_photo = None
        
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
        """Obtiene un frame de la cámara y lo convierte a formato Pygame."""
        if self.camera is None or not self.camera.isOpened():
            return None
        
        ret, frame = self.camera.read()
        if not ret:
            return None
        
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
        
        # Generar nombre de archivo con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"photobooth_{timestamp}.jpg"
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
        image = ImageOps.expand(image, border=PICTURE_BORDER_SIZE, fill=PICTURE_BODER_COLOR)
        
        # Guardar imagen modificada
        print(f"Foto guardada como {filepath}")
        
        # Convertir la imagen para mostrarla en pygame
        pygame_image = pygame.image.load(filepath)
        pygame_image = pygame.transform.scale(pygame_image, (SCREEN_WIDTH, SCREEN_HEIGHT))
        
        self.last_photo = pygame_image
        return filepath
    
    def print_photo(self, filepath):
        """Envía la foto a la impresora en un hilo separado."""
        if not self.printer_name or not self.conn:
            print("Sistema de impresión no disponible. La foto se guardará sin imprimir.")
            return False
        
        def print_job():
            try:
                print(f"Imprimiendo foto: {filepath}")
                job_id = self.conn.printFile(
                    self.printer_name, 
                    filepath, 
                    "Photobooth Image", 
                    {}
                )
                print(f"Trabajo de impresión enviado. ID: {job_id}")
            except Exception as e:
                print(f"Error al imprimir: {e}")
        
        # Iniciar la impresión en un hilo separado para no bloquear la interfaz
        print_thread = threading.Thread(target=print_job)
        print_thread.daemon = True
        print_thread.start()
    
    def coin_detection_loop(self):
        """Bucle de detección de monedas en un hilo separado."""
        while self.running:
            if self.current_state == "waiting_coin" and GPIO.input(COIN_PIN) == GPIO.HIGH:
                print("¡Moneda detectada!")
                GPIO.output(LED_PIN, GPIO.HIGH)  # Encender LED
                self.current_state = "countdown"
                self.countdown_value = 5
                # Esperar un momento para evitar rebotes
                time.sleep(0.2)
                GPIO.output(LED_PIN, GPIO.LOW)  # Apagar LED
            time.sleep(0.1)  # Pequeña pausa para no saturar la CPU
    
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
        text1 = self.font_large.render("-- Nila's Photomat --", True, WHITE)
        text2 = self.font_medium.render("Insert 1€ to take a photo", True, WHITE)
        
        # Centrar texto
        text1_rect = text1.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 50))
        text2_rect = text2.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 50))
        
        # Dibujar texto con un resplandor
        for offset in range(1, 5, 2):
            glow_rect = text1_rect.copy()
            glow_rect.x += offset
            glow_rect.y += offset
            text_glow = self.font_large.render("INSERTAR 1 EURO", True, BLUE)
            self.screen.blit(text_glow, glow_rect)
        
        self.screen.blit(text1, text1_rect)
        self.screen.blit(text2, text2_rect)
    
    def draw_countdown_screen(self):
        """Dibuja la pantalla de cuenta regresiva."""
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
        if self.countdown_value > 3:
            prep_text = "Mira al pajarito!"
        elif self.countdown_value > 1:
            prep_text = "SONRÍE!"
        else:
            prep_text = "¡FOTO!"
            
        prep_render = self.font_medium.render(prep_text, True, WHITE)
        prep_rect = prep_render.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 150))
        self.screen.blit(prep_render, prep_rect)
    
    def draw_photo_screen(self):
        """Dibuja la pantalla con la foto tomada."""
        self.screen.fill(BLACK)
        
        if self.last_photo:
            self.screen.blit(self.last_photo, (0, 0))
            
            # Texto indicativo
            if self.printer_name and self.conn:
                text = self.font_small.render("¡Tu foto está siendo impresa!", True, WHITE)
            else:
                text = self.font_small.render("¡Tu foto ha sido guardada!", True, WHITE)
                
            text_rect = text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT - 50))
            
            # Fondo semi-transparente para el texto
            text_bg = pygame.Surface((text_rect.width + 20, text_rect.height + 10), pygame.SRCALPHA)
            text_bg.fill((0, 0, 0, 180))
            self.screen.blit(text_bg, (text_rect.x - 10, text_rect.y - 5))
            self.screen.blit(text, text_rect)
    
    def update_countdown(self):
        """Actualiza el valor de la cuenta regresiva."""
        if self.current_state == "countdown":
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
                
                # Si la cuenta llega a cero, tomar foto
                if self.countdown_value <= 0:
                    # Flash effect
                    self.screen.fill(WHITE)
                    pygame.display.flip()
                    pygame.time.delay(100)
                    
                    # Tomar y mostrar foto
                    filepath = self.take_photo()
                    if filepath:
                        self.print_photo(filepath)
                    
                    self.current_state = "show_photo"
                    self.photo_display_start = pygame.time.get_ticks()
    
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
                            self.current_state = "countdown"
                            self.countdown_value = 5
                
                # Actualizar estado
                if self.current_state == "countdown":
                    self.update_countdown()
                elif self.current_state == "show_photo":
                    # Mostrar la foto durante 5 segundos
                    current_time = pygame.time.get_ticks()
                    if not hasattr(self, 'photo_display_start'):
                        self.photo_display_start = current_time
                    
                    if current_time - self.photo_display_start >= 5000:  # 5 segundos
                        self.current_state = "waiting_coin"
                        delattr(self, 'photo_display_start')
                
                # Dibujar pantalla según el estado actual
                if self.current_state == "waiting_coin":
                    self.draw_waiting_screen()
                elif self.current_state == "countdown":
                    self.draw_countdown_screen()
                elif self.current_state == "show_photo":
                    self.draw_photo_screen()
                
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