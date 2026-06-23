import operator
import random
import numpy as np
import pandas as pd
import multiprocessing
import glob
import os
from deap import base, creator, tools, gp, algorithms

# ==========================================
# PARÁMETROS PRINCIPALES DE LA SIMULACIÓN
# ==========================================
NUM_FASES       = 10   # entornos distintos a recorrer
GEN_POR_FASE    = 5    # generaciones por fase
TAM_POBLACION   = 50   # individuos por generación
TAM_ELITE       = 10   # semilla transferida entre fases
MAX_TREE_HEIGHT = 8    # límite de altura, controla bloat
NUM_INSTANCIAS  = 10   # instancias knapsack por fase
NUM_OBJETOS     = 50   # objetos por instancia

FASE_ACTUAL = 1

# ==========================================
# ESTRUCTURAS DEL PROBLEMA KNAPSACK
# ==========================================
class Item:
    def __init__(self, id_item, weight, profit):
        self.id     = id_item
        self.weight = weight
        self.profit = profit

class KnapsackInstance:
    def __init__(self, id_instancia, capacity, items):
        self.id       = id_instancia
        self.capacity = capacity
        # OPTIMIZACIÓN 1: Vectorización. Almacenamos pesos y beneficios en arreglos NumPy
        # Esto permite evaluar todos los objetos de golpe sin bucles lentos en Python.
        self.profits = np.array([item.profit for item in items], dtype=float)
        self.weights = np.array([item.weight for item in items], dtype=float)
        self.ratios  = self.profits / self.weights

# ==========================================
# CONFIGURACIÓN DEL ÁRBOL GP (PRIMITIVAS)
# ==========================================
def div_segura(izq, der):
    # OPTIMIZACIÓN 1b: División vectorizada a prueba de fallos
    # np.where permite hacer la operación sobre todo el vector simultáneamente
    return np.where(np.abs(der) > 1e-6, izq / der, 1.0)

pset = gp.PrimitiveSet("MAIN", 3)
pset.addPrimitive(np.add, 2, name="add")
pset.addPrimitive(np.subtract, 2, name="sub")
pset.addPrimitive(np.multiply, 2, name="mul")
pset.addPrimitive(div_segura, 2, name="div")

# OPTIMIZACIÓN 2: Constantes efímeras (ERCs). 
# Permitimos al GP usar números aleatorios fijos en los árboles, 
# dándole más libertad matemática.
def rand101():
    return random.uniform(-1, 1)

pset.addEphemeralConstant("rand101", rand101)

pset.renameArguments(ARG0='P', ARG1='W', ARG2='PW')

# ==========================================
# CONFIGURACIÓN DEAP
# ==========================================
if not hasattr(creator, "FitnessMax"):
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
if not hasattr(creator, "Individual"):
    creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax)

toolbox = base.Toolbox()
toolbox.register("expr",       gp.genHalfAndHalf,  pset=pset, min_=1, max_=3)
toolbox.register("individual", tools.initIterate,   creator.Individual, toolbox.expr)
toolbox.register("population", tools.initRepeat,    list, toolbox.individual)
toolbox.register("compile",    gp.compile,          pset=pset)

toolbox.register("select", tools.selTournament, tournsize=3)
toolbox.register("mate",   gp.cxOnePoint)
toolbox.register("mutate", gp.mutUniform, expr=toolbox.expr, pset=pset)

toolbox.decorate("mate",   gp.staticLimit(key=operator.attrgetter("height"), max_value=MAX_TREE_HEIGHT))
toolbox.decorate("mutate", gp.staticLimit(key=operator.attrgetter("height"), max_value=MAX_TREE_HEIGHT))

# ==========================================
# EVALUACIÓN DE FITNESS
# ==========================================
def evaluar_robusto(individuo, lista_instancias):
    try:
        rutina_puntuacion = toolbox.compile(expr=individuo)
    except Exception:
        return (-np.inf,)

    ganancias = []
    for instancia in lista_instancias:
        try:
            # OPTIMIZACIÓN 1c: Evaluación simultánea. 
            # Le pasamos arreglos de NumPy y nos devuelve un arreglo de puntuaciones
            scores = rutina_puntuacion(instancia.profits, instancia.weights, instancia.ratios)
            
            # Si el árbol es solo una constante (no depende de las variables),
            # numpy devuelve un escalar. Lo convertimos en arreglo del tamaño correcto.
            if np.isscalar(scores):
                scores = np.full_like(instancia.profits, scores)

            # Ordenamos los índices de los objetos por puntuación de forma descendente
            indices_ordenados = np.argsort(-scores)
            
            # Obtenemos los pesos y ganancias ya ordenados
            w_sorted = instancia.weights[indices_ordenados]
            p_sorted = instancia.profits[indices_ordenados]

            # OPTIMIZACIÓN 4: Empaquetado "Greedy" ultrarrápido usando variables locales
            peso_actual = 0.0
            ganancia_actual = 0.0
            
            for w, p in zip(w_sorted, p_sorted):
                if peso_actual + w <= instancia.capacity:
                    peso_actual += w
                    ganancia_actual += p
                    
            ganancias.append(ganancia_actual)
            
        except Exception:
            # Cualquier desbordamiento o error se penaliza descartando el individuo
            return (-np.inf,)

    if not ganancias:
        return (-np.inf,)

    penalizacion = len(individuo) * 0.01
    return (np.mean(ganancias) - penalizacion,)

# ==========================================
# ENTORNO DINÁMICO Y EVOLUCIÓN
# ==========================================
def generar_base_datos_aleatoria(num_instancias=NUM_INSTANCIAS, num_objetos=NUM_OBJETOS):
    instancias = []
    for i in range(num_instancias):
        capacidad = random.uniform(50.0, 150.0)
        objetos   = [Item(j, random.uniform(1.0, 20.0), random.uniform(10.0, 100.0))
                     for j in range(num_objetos)]
        instancias.append(KnapsackInstance(f"Inst_{i}", capacidad, objetos))
    return instancias

def clasificar_y_evolucionar(lista_instancias, generaciones=GEN_POR_FASE, elite_anterior=None):
    global FASE_ACTUAL

    if elite_anterior:
        poblacion = [toolbox.clone(ind) for ind in elite_anterior]
        while len(poblacion) < TAM_POBLACION:
            poblacion.append(toolbox.individual())
    else:
        poblacion = toolbox.population(n=TAM_POBLACION)

    # Re-inyectar la evaluación apuntando a la nueva base de datos
    toolbox.register("evaluate", evaluar_robusto, lista_instancias=lista_instancias)

    for ind in poblacion:
        del ind.fitness.values

    estadisticas = tools.Statistics(lambda ind: ind.fitness.values[0] if ind.fitness.valid else -np.inf)
    estadisticas.register("Promedio",     np.mean)
    estadisticas.register("Max_Ganancia", np.max)
    estadisticas.register("Desviacion",   np.std)
    
    salon_fama = tools.HallOfFame(TAM_ELITE)

    # OPTIMIZACIÓN 3: Elitismo Activo (eaMuPlusLambda)
    # Selecciona siempre los mejores entre padres E hijos, garantizando que el mejor
    # individuo jamás se pierda accidentalmente por una mala mutación.
    poblacion_final, bitacora = algorithms.eaMuPlusLambda(
        poblacion, toolbox,
        mu=TAM_POBLACION, lambda_=TAM_POBLACION,
        cxpb=0.7, mutpb=0.2,
        ngen=generaciones,
        stats=estadisticas,
        halloffame=salon_fama,
        verbose=True
    )

    df_log = pd.DataFrame(bitacora)
    df_log.insert(0, "fase", FASE_ACTUAL)
    
    mejor = salon_fama[0]
    with open(f"Fase{FASE_ACTUAL:02d}_mejor_regla.txt", "w") as f:
        f.write(f"Fase {FASE_ACTUAL} - Mejor hiper-heuristica\n")
        f.write(str(mejor) + "\n\n")
        f.write(f"Fitness: {mejor.fitness.values[0]:.4f}\n")
        f.write(f"Nodos: {len(mejor)}  |  Altura: {mejor.height}\n")

    return list(salon_fama), df_log

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
if __name__ == "__main__":
    # OPTIMIZACIÓN 5: Procesamiento en Paralelo (Multiprocessing)
    # Evaluamos a múltiples individuos de la población al mismo tiempo usando todos los hilos del CPU.
    pool = multiprocessing.Pool()
    toolbox.register("map", pool.map)

    # Limpiar archivos anteriores
    for patron in ["Fase*_mejor_regla.txt", "resumen_completo.csv"]:
        for archivo in glob.glob(patron):
            os.remove(archivo)

    pool_elite = None
    todas_las_bitacoras = []

    for nueva_fase in range(1, NUM_FASES + 1):
        FASE_ACTUAL = nueva_fase
        base_de_datos = generar_base_datos_aleatoria()
        
        # Ejecutar la fase evolutiva
        pool_elite, df_bitacora = clasificar_y_evolucionar(
            base_de_datos,
            generaciones=GEN_POR_FASE,
            elite_anterior=pool_elite
        )
        todas_las_bitacoras.append(df_bitacora)

    # OPTIMIZACIÓN 6: Concatenación eficiente de DataFrames en memoria.
    if todas_las_bitacoras:
        resumen = pd.concat(todas_las_bitacoras, ignore_index=True)
        resumen.to_csv("resumen_completo.csv", index=False)
        print("\n--- RESUMEN POR FASE ---")
        print(resumen.groupby("fase")["Max_Ganancia"].max().to_string())

    print("\n--- MEJOR HIPER-HEURÍSTICA FINAL ---")
    print(pool_elite[0])
    
    # Cerrar el pool de multiprocessing
    pool.close()
    pool.join()