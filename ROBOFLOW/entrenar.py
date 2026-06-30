import os
from ultralytics import YOLO

def main():
    print("1. El dataset ya está descargado localmente.")
    dataset_location = r"C:\Users\jrhe0\OneDrive\Documentos\Interfaz prueba\Interfaz de prueba\prueba-casi-funcional\ROBOFLOW\Pelotas-rojas,-blancas-y-negras-1"
    
    print("\n2. Preparando modelo base YOLOv8 de SEGMENTACIÓN...")
    # Cargamos el modelo de segmentación para recuperar la funcionalidad del "contorno"
    model = YOLO("yolov8n-seg.pt")
    
    print(f"\n3. Iniciando entrenamiento usando el dataset en: {dataset_location}")
    # imgsz=480 para igualar a la resolución de nuestra app
    # project="entrenamiento" y name="mi_modelo" definirán la carpeta de salida
    results = model.train(
        data=f"{dataset_location}/data.yaml",
        epochs=50,
        imgsz=480,
        batch=16,
        project=r"C:\Users\jrhe0\OneDrive\Documentos\Interfaz prueba\Interfaz de prueba\prueba-casi-funcional\ROBOFLOW\entrenamiento_seg",
        name="mi_modelo_seg"
    )
    
    print("\n ¡Entrenamiento completado exitosamente!")
    print("El archivo 'best.pt' resultante se encuentra en la carpeta: ROBOFLOW/entrenamiento_seg/mi_modelo_seg/weights/best.pt")

if __name__ == '__main__':
    main()
