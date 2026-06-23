# Celda 3 - UI y Optimizacion OpenCV DEAP ABSOLUTO  [V0.6]
import customtkinter as ctk
from PIL import Image
import threading

class EscanerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('Deteccion de Carga - V14 (Anti-Ghost)')
        self.geometry('1380x860')
        self.configure(fg_color='#1a1d2e')
        
        self.cap = None
        self.escaneando = False
        self.cache_visual = FrameQualityCache(history_size=3)
        
        self.trackers = {
            'Rojo': [TrackerCirculo() for _ in range(LIMITES_PELOTAS['Rojo'])],
            'Blanco': [TrackerCirculo() for _ in range(LIMITES_PELOTAS['Blanco'])],
            'Negro': [TrackerCirculo() for _ in range(LIMITES_PELOTAS['Negro'])]
        }
        self.temporizadores = {
            'Rojo': [0.0]*LIMITES_PELOTAS['Rojo'],
            'Blanco': [0.0]*LIMITES_PELOTAS['Blanco'],
            'Negro': [0.0]*LIMITES_PELOTAS['Negro']
        }
        self.historial_objetos = set()
        self.puntos_actuales = 0
        self.limite_alcanzado = False
        
        self.cam_delay_ms = 33

        ruta_modelo = r"C:\Users\jrhe0\.gemini\antigravity-ide\scratch\detector_pelotas\models\entrenamiento_pelotas\weights\best.pt"
        if os.path.exists(ruta_modelo):
            print("Cargando modelo de IA (YOLOv8)...")
            self.modelo_yolo = YOLO(ruta_modelo)
        else:
            print("ERROR: No se encontro el modelo YOLO en " + ruta_modelo)
            self.modelo_yolo = None
        self._construir_ui()
        self._auto_check_camaras()

    def _construir_ui(self):
        self.lbl_titulo = ctk.CTkLabel(self, text='CONFIGURACION DE CAMARA', font=('Helvetica', 22, 'bold'), text_color='#e8eaf0')
        self.lbl_titulo.pack(pady=(28, 12))
        self.panel_config = ctk.CTkFrame(self, fg_color='transparent')
        self.panel_config.pack(expand=True, fill='both')
        
        self.btn_detectar = ctk.CTkButton(self.panel_config, text='DETECTAR CAMARAS', command=self._accion_buscar)
        self.btn_detectar.pack(pady=10)
        self.frame_lista = ctk.CTkScrollableFrame(self.panel_config, width=700, height=150)
        self.frame_lista.pack(pady=5)
        self.indice_sel = ctk.StringVar(value='-1')
        self.btn_iniciar = ctk.CTkButton(self.panel_config, text='INICIAR DETECCION', state='disabled', command=self._iniciar_camara)
        self.btn_iniciar.pack(pady=40)
        
        self.panel_video = ctk.CTkFrame(self, fg_color='transparent')
        self.lbl_video = ctk.CTkLabel(self.panel_video, text='')
        self.lbl_video.pack(pady=10, padx=10)
        
        self.frame_controles = ctk.CTkFrame(self.panel_video, fg_color='transparent')
        self.frame_controles.pack(pady=8)
        
        self.btn_escaneo = ctk.CTkButton(self.frame_controles, text='Iniciar Escaneo', command=self._toggle_escaneo)
        self.btn_escaneo.grid(row=0, column=0, padx=10)
        
        self.btn_limpiar = ctk.CTkButton(self.frame_controles, text='Limpiar Todo', command=self._limpiar_todo)
        self.btn_limpiar.grid(row=0, column=1, padx=10)
        
        self.btn_detener = ctk.CTkButton(self.frame_controles, text='Dejar de Escanear', fg_color='#e74c3c', hover_color='#c0392b', command=self._detener_camara)
        self.btn_detener.grid(row=0, column=2, padx=10)
        
        self.lbl_puntos = ctk.CTkLabel(self.frame_controles, text='Puntos: 0 / 10 MAX', font=('Helvetica', 16, 'bold'), text_color='#3498db')
        self.lbl_puntos.grid(row=0, column=3, padx=20)
        
        self.lbl_gp_status = ctk.CTkLabel(self.panel_video, text='', text_color='#f1c40f', font=('Helvetica', 14, 'bold'))
        self.lbl_gp_status.pack(pady=5)

        self.lista_scroll = ctk.CTkScrollableFrame(self.panel_video, width=300)
        self.lista_scroll.pack(side='right', fill='y', padx=10, pady=10)

    def _auto_check_camaras(self):
        if self.cap is not None and self.cap.isOpened():
            self.after(2000, self._auto_check_camaras)
            return
            
        camaras = detectar_camaras_sistema()
        nombres_camaras = [n for _, n in camaras]
        
        if not hasattr(self, 'ultimas_camaras'):
            self.ultimas_camaras = []
            
        if nombres_camaras != self.ultimas_camaras:
            self.ultimas_camaras = nombres_camaras
            self._accion_buscar(camaras)
            
        self.after(2000, self._auto_check_camaras)

    def _accion_buscar(self, camaras=None):
        if camaras is None:
            camaras = detectar_camaras_sistema()
            self.ultimas_camaras = [n for _, n in camaras]
            
        for w in self.frame_lista.winfo_children(): w.destroy()
        if camaras:
            current_sel = self.indice_sel.get()
            for idx, etq in camaras:
                ctk.CTkRadioButton(self.frame_lista, text=etq, variable=self.indice_sel, value=str(idx)).pack(anchor='w', pady=5)
            if not any(str(idx) == current_sel for idx, _ in camaras):
                self.indice_sel.set(str(camaras[0][0]))
            self.btn_iniciar.configure(state='normal')
        else:
            self.btn_iniciar.configure(state='disabled')
            self.indice_sel.set('-1')

    def _iniciar_camara(self):
        idx = int(self.indice_sel.get())
        if idx == -1: return
        self.panel_config.pack_forget()
        self.panel_video.pack(expand=True, fill='both')
        self.lbl_titulo.configure(text='MONITOR EN VIVO (V14)')
        
        self.cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not self.cap.isOpened() or not self.cap.read()[0]:
            self.cap = cv2.VideoCapture(idx)
            
        if not self.cap.isOpened():
            self.lbl_video.configure(text='ERROR', text_color='red')
            return
            
        self.lbl_video.configure(text='')
        self.escaneando = False
        self.cache_visual = FrameQualityCache(history_size=3)
        self._loop_video()

    def _detener_camara(self):
        self.escaneando = False
        if self.cap: self.cap.release()
        self.panel_video.pack_forget()
        self.panel_config.pack(expand=True, fill='both')

    def _toggle_escaneo(self):
        self.escaneando = not self.escaneando
        if self.escaneando: self.btn_escaneo.configure(text='Pausar Escaneo', fg_color='#d35400')
        else: self.btn_escaneo.configure(text='Reanudar Escaneo', fg_color='#f39c12')

    def _loop_video(self):
        if not self.cap or not self.cap.isOpened(): return
        
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            # ── RETICULA SIEMPRE VISIBLE ──────────────────────
            dibujar_reticula(frame)
            # ── Deteccion solo cuando escaneo esta activo ─────
            if self.escaneando and not self.limite_alcanzado:
                if self.modelo_yolo is not None:
                    frame, _ = procesar_frame_vision_yolo(
                        frame, self.temporizadores, self.trackers, self.modelo_yolo,
                        cache_visual=self.cache_visual,
                        callback_objeto=self.on_objeto_detectado
                    )
                else:
                    cv2.putText(frame, "ERROR: YOLO NO CARGADO", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            img = ctk.CTkImage(light_image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), size=(920, 630))
            self.lbl_video.configure(image=img)
        
        self.after(self.cam_delay_ms, self._loop_video)

    def on_objeto_detectado(self, lbl_nombre, x, y, z):
        if self.limite_alcanzado: return
        
        if lbl_nombre not in self.historial_objetos:
            pts = 0
            if 'Negro' in lbl_nombre: pts = 5
            elif 'Blanco' in lbl_nombre: pts = 3
            elif 'Rojo' in lbl_nombre: pts = 1
            
            if self.puntos_actuales + pts > 10:
                self.historial_objetos.add(lbl_nombre)
                self.puntos_actuales += pts
                self.limite_alcanzado = True
                self.escaneando = False
                ctk.CTkLabel(self.lista_scroll, text=f"{lbl_nombre} (+{pts} pts) -> ¡LIMITE!").pack()
                self.lbl_puntos.configure(text=f'Puntos: {self.puntos_actuales} / 10 MAX', text_color='red')
                self.btn_escaneo.configure(text='Límite Alcanzado', state='disabled', fg_color='#7f8c8d')
                self.lbl_gp_status.configure(text=f'¡CANASTA LLENA! ({self.puntos_actuales} pts detectados)', text_color='red')
                return

            self.historial_objetos.add(lbl_nombre)
            self.puntos_actuales += pts
            ctk.CTkLabel(self.lista_scroll, text=f"{lbl_nombre} (+{pts} pts)").pack()
            self.lbl_puntos.configure(text=f'Puntos: {self.puntos_actuales} / 10 MAX')
            
            if self.puntos_actuales == 10:
                self.limite_alcanzado = True
                self.escaneando = False
                self.btn_escaneo.configure(text='Límite Alcanzado', state='disabled', fg_color='#7f8c8d')
                self.lbl_gp_status.configure(text=f'¡CANASTA LLENA! (10 pts)', text_color='red')
                self.lbl_puntos.configure(text_color='red')

    def _limpiar_todo(self):
        for w in self.lista_scroll.winfo_children(): w.destroy()
        self.historial_objetos.clear()
        self.puntos_actuales = 0
        self.limite_alcanzado = False
        self.lbl_puntos.configure(text='Puntos: 0 / 10 MAX', text_color='#3498db')
        self.lbl_gp_status.configure(text='')
        self.btn_escaneo.configure(state='normal', text='Iniciar Escaneo', fg_color='#1f6aa5')
        self.escaneando = False
        for c in self.temporizadores: self.temporizadores[c] = [0.0]*LIMITES_PELOTAS[c]
        for c in self.trackers: 
            for tr in self.trackers[c]: tr.reiniciar()

print('Celda 4 V14 lista.')
