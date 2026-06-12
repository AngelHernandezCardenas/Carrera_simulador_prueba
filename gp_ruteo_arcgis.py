import operator
import random
import time
import numpy as np
import pandas as pd
from datetime import datetime
from deap import base, creator, tools, gp, algorithms

# ==========================================
# PARÁMETROS DEL OPTIMIZADOR
# ==========================================
TAM_POBLACION   = 50   
MAX_TREE_HEIGHT = 6    # Reducido para favorecer ecuaciones rápidas y ejecutables

# ==========================================
# 1. NUEVAS PRIMITIVAS MATEMÁTICAS (Cálculo y Álgebra)
# ==========================================
def div_segura(izq, der): 
    return np.where(np.abs(der) > 1e-6, izq / der, 1.0)

def log_seguro(val): 
    # Evita logaritmo de cero o negativos (usa valor absoluto)
    return np.log(np.clip(np.abs(val), 1e-6, None))

def exp_segura(val): 
    # Evita overflow en exponenciales muy grandes
    return np.exp(np.clip(val, -10, 10))

pset = gp.PrimitiveSet("MAIN", 5)
pset.addPrimitive(np.add, 2)
pset.addPrimitive(np.subtract, 2)
pset.addPrimitive(np.multiply, 2)
pset.addPrimitive(div_segura, 2)
pset.addPrimitive(np.sin, 1)
pset.addPrimitive(np.cos, 1)
pset.addPrimitive(exp_segura, 1)
pset.addPrimitive(log_seguro, 1)

def rand101(): 
    return random.uniform(-1, 1)
pset.addEphemeralConstant("rand101", rand101)

# TERMINALES DEL PROBLEMA (Variables de estado dinámicas)
# Pila: Nivel actual (0-100)
# Carga: Pelotas/paquetes en kg o unidades
# Emisiones: Nivel actual de emisiones generadas
# DPila: Delta Pila (derivada discreta, ej. pérdida de batería por segundo)
# DEmisiones: Delta Emisiones (derivada discreta)
pset.renameArguments(ARG0='Pila', ARG1='Carga', ARG2='Emisiones', ARG3='DPila', ARG4='DEmisiones')

# ==========================================
# CONFIGURACIÓN DEAP
# ==========================================
# Queremos MAXIMIZAR la eficiencia de la ruta
if not hasattr(creator, "FitnessMax"):
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
if not hasattr(creator, "Individual"):
    creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax)

toolbox = base.Toolbox()
toolbox.register("expr", gp.genHalfAndHalf, pset=pset, min_=1, max_=3)
toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.expr)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("compile", gp.compile, pset=pset)

toolbox.register("select", tools.selTournament, tournsize=3)
toolbox.register("mate", gp.cxOnePoint)
toolbox.register("mutate", gp.mutUniform, expr=toolbox.expr, pset=pset)

toolbox.decorate("mate", gp.staticLimit(key=operator.attrgetter("height"), max_value=MAX_TREE_HEIGHT))
toolbox.decorate("mutate", gp.staticLimit(key=operator.attrgetter("height"), max_value=MAX_TREE_HEIGHT))

# ==========================================
# FUNCIÓN OBJETIVO (FITNESS EN TIEMPO REAL)
# ==========================================
def evaluar_ruta(individuo, datos_arcgis):
    try:
        # El individuo es una función diferencial generada (e.g. sin(Pila) + exp(Carga))
        func_ruta = toolbox.compile(expr=individuo)
        
        Pila       = datos_arcgis['Pila'].values
        Carga      = datos_arcgis['Carga'].values
        Emisiones  = datos_arcgis['Emisiones'].values
        DPila      = datos_arcgis['DPila'].values
        DEmisiones = datos_arcgis['DEmisiones'].values
        
        # Aplicamos la ecuación a todos los ciclistas/nodos al mismo tiempo
        scores = func_ruta(Pila, Carga, Emisiones, DPila, DEmisiones)
        
        if np.isscalar(scores):
            scores = np.full_like(Pila, scores)
            
        # FITNESS SIMULADO:
        # Supongamos que la ecuación generada (el score) se usa para decidir
        # a qué 30% de ciclistas priorizar o qué tramos recorrer.
        indices_elegidos = np.argsort(-scores)[:max(1, len(scores)//3)]
        
        carga_total     = np.sum(Carga[indices_elegidos])
        pila_gastada    = np.sum(np.abs(DPila[indices_elegidos]))  # DPila suele ser negativo
        emisiones_total = np.sum(DEmisiones[indices_elegidos])
        
        # Premiar mucha carga. Penalizar pérdida de pila y altas emisiones.
        # Esto entrenará a la ecuación para elegir rutas/ciclistas óptimos.
        fitness_val = (carga_total * 10.0) - (pila_gastada * 5.0) - (emisiones_total * 2.0)
        
        # Presión de parsimonia (bloat control)
        fitness_val -= len(individuo) * 0.1
        
        return (fitness_val,)
    except Exception:
        # Si la ecuación falla (overflow, NaN), se muere.
        return (-np.inf,)

# ==========================================
# LECTURA DE DATOS ARCGIS (GeoJSON)
# ==========================================
import json
import os

# Diccionario global para guardar el estado anterior y calcular derivadas (Deltas)
estado_anterior = {}

def leer_datos_arcgis_geojson(ruta_archivo='gps_data.geojson'):
    global estado_anterior
    
    if not os.path.exists(ruta_archivo):
        print(f"⚠️ Archivo {ruta_archivo} no encontrado. Esperando datos...")
        return pd.DataFrame()
        
    try:
        with open(ruta_archivo, 'r') as f:
            data = json.load(f)
            
        features = data.get("features", [])
        if not features:
            print(" Archivo GeoJSON vacío. Esperando registros...")
            return pd.DataFrame()
            
        registros = []
        
        for i, feat in enumerate(features):
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [0.0, 0.0])
            
            # Buscamos IDs o asignamos uno temporal
            bicicleta_id = props.get("Bicicleta_ID", props.get("id", i))
            
            # Buscamos variables en las propiedades (fallback a valores por defecto)
            pila = props.get("Pila", 100.0)
            carga = props.get("Carga", 0.0)
            emisiones = props.get("Emisiones", 0.0)
            
            # Calcular Deltas basados en el ciclo anterior
            dpila = 0.0
            demisiones = 0.0
            
            if bicicleta_id in estado_anterior:
                dpila = pila - estado_anterior[bicicleta_id]['Pila']
                demisiones = emisiones - estado_anterior[bicicleta_id]['Emisiones']
                
            estado_anterior[bicicleta_id] = {
                'Pila': pila,
                'Emisiones': emisiones
            }
            
            registros.append({
                'Bicicleta_ID': bicicleta_id,
                'Pila': pila,
                'Carga': carga,
                'Emisiones': emisiones,
                'DPila': dpila,
                'DEmisiones': demisiones,
                'Longitud': coords[0],
                'Latitud': coords[1] if len(coords) > 1 else 0.0
            })
            
        return pd.DataFrame(registros)
        
    except Exception as e:
        print(f"Error leyendo GeoJSON: {e}")
        return pd.DataFrame()

# ==========================================
# BUCLE PRINCIPAL (TICK CADA 3 SEGUNDOS)
# ==========================================
def optimizador_tiempo_real():
    poblacion = toolbox.population(n=TAM_POBLACION)
    salon_fama = tools.HallOfFame(1)
    
    print("Iniciando Motor GP de Ruteo Continuo para ArcGIS...")
    
    # Aquí almacenaremos los registros para exportar a Parquet/CSV
    historico_registros = []
    
    ciclo = 1
    try:
        while True: 
            inicio_tick = time.time()
            print(f"\n--- Tick #{ciclo} ---")
            
            # 1. LEER DATOS (GeoJSON sincronizado con ArcGIS)
            df_arcgis = leer_datos_arcgis_geojson('gps_data.geojson')
            
            # Si no hay datos nuevos, esperar al siguiente ciclo
            if df_arcgis.empty:
                tiempo_espera = max(0, 3.0 - (time.time() - inicio_tick))
                time.sleep(tiempo_espera)
                ciclo += 1
                continue
                
            df_arcgis['Tick'] = ciclo
            df_arcgis['Timestamp'] = datetime.now()
            
            # 2. ACTUALIZAR FUNCIÓN DE FITNESS CON LOS DATOS NUEVOS
            toolbox.register("evaluate", evaluar_ruta, datos_arcgis=df_arcgis)
            
            # 3. EVOLUCIÓN EN CALIENTE (Solo 2 generaciones para reaccionar rápido)
            for ind in poblacion:
                del ind.fitness.values # Forzar re-evaluación del entorno cambiante
                
            poblacion, bitacora = algorithms.eaMuPlusLambda(
                poblacion, toolbox,
                mu=TAM_POBLACION, lambda_=TAM_POBLACION,
                cxpb=0.7, mutpb=0.2,
                ngen=2,  # Rápido, ideal para optimización online
                stats=None,
                halloffame=salon_fama,
                verbose=False
            )
            
            # 4. APLICAR LA MEJOR ECUACIÓN ENCONTRADA A LOS REGISTROS
            mejor_ecuacion = salon_fama[0]
            func_mejor = toolbox.compile(expr=mejor_ecuacion)
            scores_ruta = func_mejor(
                df_arcgis['Pila'].values, 
                df_arcgis['Carga'].values, 
                df_arcgis['Emisiones'].values, 
                df_arcgis['DPila'].values, 
                df_arcgis['DEmisiones'].values
            )
            
            if np.isscalar(scores_ruta):
                scores_ruta = np.full_like(df_arcgis['Pila'].values, scores_ruta)
                
            # Asignamos el score generado por la IA al dataframe para ArcGIS
            df_arcgis['Prioridad_GP_Score'] = scores_ruta
            historico_registros.append(df_arcgis)
            
            print(f"Mejor Fitness: {mejor_ecuacion.fitness.values[0]:.2f}")
            print(f"Ecuación Gobernante: {mejor_ecuacion}")
            
            # 5. CONTROL DEL TIEMPO (Garantizar pulso máximo de 3 segundos)
            tiempo_transcurrido = time.time() - inicio_tick
            tiempo_espera = max(0, 3.0 - tiempo_transcurrido)
            print(f"Procesamiento GP: {tiempo_transcurrido:.3f}s. Esperando {tiempo_espera:.3f}s para el sig. request...")
            time.sleep(tiempo_espera)
            
            ciclo += 1
            
    except KeyboardInterrupt:
        print("\nOptimizador detenido por el usuario (KeyboardInterrupt).")
        
    # ==========================================
    # GUARDADO FINAL EN DISCO
    # ==========================================
    if historico_registros:
        print("\nGuardando registros históricos en disco...")
        df_final = pd.concat(historico_registros, ignore_index=True)
        
        # Exportar a CSV (siempre seguro)
        df_final.to_csv('registros_arcgis_rutas.csv', index=False)
        print("Guardado exitoso: 'registros_arcgis_rutas.csv'")
        
        # Intentar exportar a Parquet
        try:
            df_final.to_parquet('registros_arcgis_rutas.parquet', engine='pyarrow')
            print("Guardado exitoso: 'registros_arcgis_rutas.parquet' (Formato columnar hiper-optimizado)")
        except ImportError:
            print("NOTA: Instala 'pyarrow' (pip install pyarrow) si deseas guardar los logs en .parquet nativo.")
    else:
        print("\nNo se registraron datos en este ciclo.")

if __name__ == "__main__":
    optimizador_tiempo_real()
