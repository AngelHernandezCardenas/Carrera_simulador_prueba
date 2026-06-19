from ultralytics import YOLO
from pathlib import Path

def train_model():
    # Rutas adaptadas al proyecto actual
    BASE_DIR = Path(__file__).parent
    DATASET_YAML = BASE_DIR / "dataset.yaml"
    
    if not DATASET_YAML.exists():
        print(f"Error: No se encontró el archivo de configuración {DATASET_YAML} en {BASE_DIR}")
        print("Asegúrate de haber preparado los datos y generado el dataset.yaml antes de entrenar.")
        return

    # Cargar un modelo pre-entrenado (YOLOv8 nano es el más ligero y rápido)
    print("Cargando modelo YOLOv8n-seg base (Segmentación)...")
    model = YOLO("yolov8n-seg.pt") 
    
    # Iniciar entrenamiento
    print("Iniciando entrenamiento del modelo YOLOv8-seg para segmentar pelotas de colores...")
    
    # Parámetros de entrenamiento
    results = model.train(
        task="segment",
        data=str(DATASET_YAML),
        epochs=50,
        imgsz=640,
        batch=16,
        project=str(BASE_DIR / "models"),
        name="entrenamiento_pelotas",
        device="cpu"  # Cambiar a "0" si tienes GPU con CUDA
    )
    
    print("\n¡Entrenamiento completado!")
    print(f"El modelo final entrenado está guardado en: {BASE_DIR / 'models' / 'entrenamiento_pelotas' / 'weights' / 'best.pt'}")

if __name__ == "__main__":
    train_model()
