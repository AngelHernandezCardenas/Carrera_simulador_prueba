import json
import codecs

def update_notebook():
    with codecs.open('ColoresPrueba.ipynb', 'r', 'utf-8') as f:
        notebook = json.load(f)

    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            source = cell.get('source', [])
            if any('class TrackerCirculo:' in line for line in source):
                start_idx = -1
                end_idx = -1
                for i, line in enumerate(source):
                    if '# 8. TRACKER AVANZADO CON GAUSSIAN PROCESSES' in line:
                        start_idx = i
                    elif '# 9. DETECTOR DE MOVIMIENTO' in line:
                        end_idx = i - 1
                        break
                
                if start_idx != -1 and end_idx != -1:
                    new_code = """# 8. TRACKER AVANZADO CON GAUSSIAN PROCESSES (Agilidad 130%)
# ─────────────────────────────────────────────────────────────
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel
import warnings
warnings.filterwarnings('ignore', category=UserWarning)

class TrackerCirculo:
    \"\"\"
    Tracker con Gaussian Processes optimizado para cero efecto fantasma.
    Responde instantaneamente a los movimientos y evita predicciones residuales.
    \"\"\"
    def __init__(self, history_size=4, frames_conf=1, frames_perdida=1):
        self.history_size = history_size
        self.frames_conf = frames_conf
        self.frames_perdida = frames_perdida
        
        # GP Optimizadísimo: length_scale pequeño (reacción rápida) y noise_level bajo (confía en la cámara)
        kernel = 1.0 * RBF(length_scale=0.5) + WhiteKernel(noise_level=0.01)
        self.gp_x = GaussianProcessRegressor(kernel=kernel, optimizer=None, alpha=0.0)
        self.gp_y = GaussianProcessRegressor(kernel=kernel, optimizer=None, alpha=0.0)
        self.gp_r = GaussianProcessRegressor(kernel=kernel, optimizer=None, alpha=0.0)
        
        self.reiniciar()

    def reiniciar(self):
        self.hist_t = collections.deque(maxlen=self.history_size)
        self.hist_x = collections.deque(maxlen=self.history_size)
        self.hist_y = collections.deque(maxlen=self.history_size)
        self.hist_r = collections.deque(maxlen=self.history_size)
        self.suave = None
        self.conteo_det = 0
        self.conteo_perd = 0
        self.visible = False
        self.t = 0

    def actualizar(self, deteccion):
        self.t += 1
        if deteccion is None:
            self.conteo_det = 0
            self.conteo_perd += 1
            if self.conteo_perd >= self.frames_perdida:
                self.visible = False
                self.suave = None
                return None
            
            # Solo predice 1 frame extra si se pierde (evita efecto fantasma flotante)
            if self.visible and len(self.hist_t) >= 3:
                T = np.array(self.hist_t).reshape(-1, 1)
                t_pred = np.array([[self.t]])
                try:
                    self.gp_x.fit(T, self.hist_x)
                    self.gp_y.fit(T, self.hist_y)
                    self.gp_r.fit(T, self.hist_r)
                    px = self.gp_x.predict(t_pred)[0]
                    py = self.gp_y.predict(t_pred)[0]
                    pr = self.gp_r.predict(t_pred)[0]
                    self.suave = (px, py, pr)
                    return (int(round(px)), int(round(py)), int(round(pr)))
                except Exception:
                    pass
            return tuple(int(round(v)) for v in self.suave) if self.suave and self.visible else None

        self.conteo_perd = 0
        self.conteo_det = min(self.conteo_det + 1, self.frames_conf + 10)
        
        self.hist_t.append(self.t)
        self.hist_x.append(deteccion[0])
        self.hist_y.append(deteccion[1])
        self.hist_r.append(deteccion[2])

        if self.conteo_det < self.frames_conf:
            if self.suave is None:
                self.suave = tuple(float(v) for v in deteccion[:3])
            return None

        self.visible = True
        
        # Con deteccion presente, usamos un blend muy ágil entre medición y GP
        if len(self.hist_t) >= 3:
            T = np.array(self.hist_t).reshape(-1, 1)
            t_pred = np.array([[self.t]])
            try:
                self.gp_x.fit(T, self.hist_x)
                self.gp_y.fit(T, self.hist_y)
                self.gp_r.fit(T, self.hist_r)
                
                px = self.gp_x.predict(t_pred)[0]
                py = self.gp_y.predict(t_pred)[0]
                pr = self.gp_r.predict(t_pred)[0]
                
                # Agilidad 130%: Confiamos 85% en la deteccion real, 15% en el GP para micro-suavizado
                sx = 0.85 * deteccion[0] + 0.15 * px
                sy = 0.85 * deteccion[1] + 0.15 * py
                sr = 0.85 * deteccion[2] + 0.15 * pr
                
                self.suave = (sx, sy, sr)
                return (int(round(sx)), int(round(sy)), int(round(sr)))
            except Exception:
                pass

        # Si GP falla o no hay historial suficiente, confia 90% en la cámara
        if self.suave is None:
            self.suave = tuple(float(v) for v in deteccion[:3])
        else:
            alpha = 0.90
            sx = alpha * deteccion[0] + (1.0 - alpha) * self.suave[0]
            sy = alpha * deteccion[1] + (1.0 - alpha) * self.suave[1]
            sr = alpha * deteccion[2] + (1.0 - alpha) * self.suave[2]
            self.suave = (sx, sy, sr)
            
        return tuple(int(round(v)) for v in self.suave)
"""
                    new_lines = [line + '\\n' for line in new_code.split('\\n')]
                    new_lines[-1] = new_lines[-1].rstrip('\\n')
                    
                    cell['source'] = source[:start_idx] + new_lines + ['\\n', '\\n'] + source[end_idx:]
                    print("Se actualizo el tracker en el notebook.")

    with codecs.open('ColoresPrueba.ipynb', 'w', 'utf-8') as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)

if __name__ == '__main__':
    update_notebook()
