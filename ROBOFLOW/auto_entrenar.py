import os, sys, cv2, shutil, time, numpy as np
from pathlib import Path
from ultralytics import YOLO

BASE_DIR   = Path(__file__).resolve().parent.parent
ROBOFLOW   = BASE_DIR / "ROBOFLOW" / "Pelotas-rojas,-blancas-y-negras-1"
CAPTURAS   = BASE_DIR / "capturas"
DATASET_DS = BASE_DIR / "ROBOFLOW" / "dataset_mejorado"
OUTPUT_DIR = BASE_DIR / "ROBOFLOW" / "entrenamiento_mejorado"
NAMES = {0: "Pelota roja", 1: "Pelota blanca", 2: "Pelota negra"}
NC = 3

# Encontrar best.pt buscando recursivamente en colores/
def _find_best_pt():
    colores = BASE_DIR / "colores"
    for pt in colores.rglob("best.pt"):
        if "backup" not in pt.name:
            return pt
    return None

MODELO_ACT = _find_best_pt()

def crear_estructura():
    print("\n[1/5] Preparando dataset mejorado (incremental)...")
    for split in ["train", "valid"]:
        (DATASET_DS / split / "images").mkdir(parents=True, exist_ok=True)
        (DATASET_DS / split / "labels").mkdir(parents=True, exist_ok=True)
    for split in ["train", "valid"]:
        src_imgs = ROBOFLOW / split / "images"
        src_lbls = ROBOFLOW / split / "labels"
        dst_imgs = DATASET_DS / split / "images"
        dst_lbls = DATASET_DS / split / "labels"
        if not src_imgs.exists():
            src_imgs = ROBOFLOW / ("valid" if split == "valid" else "train") / "images"
            src_lbls = ROBOFLOW / ("valid" if split == "valid" else "train") / "labels"
        if src_imgs.exists():
            # Solo copiar si aún no existe en destino (incremental)
            cnt = 0
            for img in src_imgs.glob("*"):
                dest = dst_imgs / img.name
                if not dest.exists():
                    shutil.copy2(img, dest)
                    cnt += 1
            ya_existian = len(list(dst_imgs.glob("*")))
            print(f"   Roboflow {split}: {cnt} nuevas, {ya_existian} totales")
        if src_lbls.exists():
            for lbl in src_lbls.glob("*.txt"):
                dest = dst_lbls / lbl.name
                if not dest.exists():
                    shutil.copy2(lbl, dest)
    yaml = f"path: {DATASET_DS}\ntrain: train/images\nval: valid/images\nnc: {NC}\nnames: {list(NAMES.values())}\n"
    (DATASET_DS / "data.yaml").write_text(yaml, encoding="utf-8")
    print("   data.yaml listo")

def auto_etiquetar(modelo_yolo):
    print("\n[2/5] Auto-etiquetando capturas (incremental)...")
    jpgs = [f for f in CAPTURAS.glob("*.jpg") if "_clean" not in f.name]
    if not jpgs:
        print("   Sin capturas, omitiendo.")
        return 0
    dst_i = DATASET_DS / "train" / "images"
    dst_l = DATASET_DS / "train" / "labels"
    n = 0
    saltadas = 0
    for img_path in jpgs:
        stem = f"cap_{img_path.stem}"
        # Saltar si ya fue etiquetada en una ejecucion anterior
        if (dst_i / f"{stem}.jpg").exists() and (dst_l / f"{stem}.txt").exists():
            saltadas += 1
            continue
        fr = cv2.imread(str(img_path))
        if fr is None:
            continue
        h, w = fr.shape[:2]
        if w > 640:
            fr = cv2.resize(fr, (640, int(h * 640/w)), interpolation=cv2.INTER_AREA)
        fh, fw = fr.shape[:2]
        res = modelo_yolo.predict(fr, conf=0.25, iou=0.35, imgsz=640, verbose=False)
        if not res or res[0].boxes is None or len(res[0].boxes) == 0:
            continue
        bx = res[0].boxes
        mk = res[0].masks if hasattr(res[0], "masks") and res[0].masks is not None else None
        lineas = []
        for i in range(len(bx)):
            cid = int(bx.cls[i].item())
            cf  = float(bx.conf[i].item())
            if cf < 0.25:
                continue
            if mk is not None and mk.xy is not None and len(mk.xy) > i:
                seg = mk.xy[i]
                if len(seg) >= 3:
                    pts = " ".join(f"{x/fw:.6f} {y/fh:.6f}" for x, y in seg)
                    lineas.append(f"{cid} {pts}")
                    continue
            x1, y1, x2, y2 = bx.xyxy[i].tolist()
            lineas.append(f"{cid} {((x1+x2)/2)/fw:.6f} {((y1+y2)/2)/fh:.6f} {(x2-x1)/fw:.6f} {(y2-y1)/fh:.6f}")
        if not lineas:
            continue
        cv2.imwrite(str(dst_i / f"{stem}.jpg"), fr)
        (dst_l / f"{stem}.txt").write_text("\n".join(lineas), encoding="utf-8")
        n += 1
    print(f"   {n} nuevas capturas etiquetadas | {saltadas} ya procesadas anteriormente")
    return n

def _flip_h(lbl):
    out = []
    for ln in lbl.strip().split("\n"):
        if not ln.strip():
            continue
        p = ln.split()
        c, coords = p[0], list(map(float, p[1:]))
        if len(coords) == 4:
            coords[0] = 1.0 - coords[0]
        else:
            for j in range(0, len(coords), 2):
                coords[j] = 1.0 - coords[j]
        out.append(c + " " + " ".join(f"{v:.6f}" for v in coords))
    return "\n".join(out)

def augmentar():
    print("\n[3/5] Augmentation...")
    dst_i = DATASET_DS / "train" / "images"
    dst_l = DATASET_DS / "train" / "labels"
    n = 0
    for ip in list(dst_i.glob("cap_*.jpg")):
        lp = dst_l / (ip.stem + ".txt")
        if not lp.exists():
            continue
        f = cv2.imread(str(ip))
        lb = lp.read_text(encoding="utf-8")
        for sfx, aug_f, aug_l in [
            ("bright", cv2.convertScaleAbs(f, alpha=1.4, beta=30), lb),
            ("dark",   cv2.convertScaleAbs(f, alpha=0.6, beta=-20), lb),
            ("flip",   cv2.flip(f, 1), _flip_h(lb)),
            ("blur",   cv2.GaussianBlur(f, (5, 5), 0), lb),
        ]:
            cv2.imwrite(str(dst_i / f"{ip.stem}_{sfx}.jpg"), aug_f)
            (dst_l / f"{ip.stem}_{sfx}.txt").write_text(aug_l, encoding="utf-8")
            n += 1
    print(f"   {n} variantes generadas")

def _find_mejor_base():
    """
    Jerarquía de base para transfer learning (de mejor a peor):
      1. El modelo ya entrenado por auto_entrenar (entrenamiento_mejorado/run/weights/best.pt)
      2. El modelo activo en produccion (best.pt)
      3. YOLOv8n-seg pretrained desde internet
    """
    candidato_mejorado = OUTPUT_DIR / "run" / "weights" / "best.pt"
    if candidato_mejorado.exists():
        print(f"   Transfer learning desde modelo mejorado previo: {candidato_mejorado.name}")
        return str(candidato_mejorado)
    if MODELO_ACT and MODELO_ACT.exists():
        print(f"   Transfer learning desde modelo en produccion: {MODELO_ACT.name}")
        return str(MODELO_ACT)
    print("   Usando yolov8n-seg.pt (sin modelo previo)")
    return "yolov8n-seg.pt"

def entrenar():
    print("\n[4/5] Entrenando modelo mejorado (incremental)...")
    t = len(list((DATASET_DS/"train"/"images").glob("*.jpg")))
    v = len(list((DATASET_DS/"valid"/"images").glob("*.jpg")))
    print(f"   Dataset: {t} train | {v} val")
    base = _find_mejor_base()
    model = YOLO(base)
    model.train(
        data=str(DATASET_DS/"data.yaml"), epochs=60, imgsz=640, batch=8, patience=20,
        lr0=0.003,   # LR mas bajo para no destruir lo aprendido
        lrf=0.001, warmup_epochs=2, mosaic=0.8, mixup=0.1,
        degrees=10.0, scale=0.5, fliplr=0.5, flipud=0.1,
        hsv_h=0.02, hsv_s=0.5, hsv_v=0.4, overlap_mask=True,
        project=str(OUTPUT_DIR), name="run", exist_ok=True, verbose=True,
    )
    return OUTPUT_DIR / "run" / "weights" / "best.pt"

def desplegar(nuevo):
    print("\n[5/5] Desplegando...")
    nuevo = Path(nuevo)
    if not nuevo.exists():
        print("   ERROR: modelo no encontrado.")
        return
    if MODELO_ACT and MODELO_ACT.exists():
        bak = MODELO_ACT.parent / f"best_backup_{int(time.time())}.pt"
        shutil.copy2(MODELO_ACT, bak)
        print(f"   Backup: {bak.name}")
    shutil.copy2(nuevo, MODELO_ACT)
    print(f"   DESPLEGADO: {MODELO_ACT}")
    print("   >> REINICIA el servidor Python para activarlo. <<")

def main():
    print("=" * 60)
    print("  AUTO-ENTRENAMIENTO INCREMENTAL v1.0")
    print(f"  Modelo actual: {MODELO_ACT}")
    print("=" * 60)
    if not MODELO_ACT:
        print("ERROR: No se encontro best.pt.")
        return
    modelo = YOLO(str(MODELO_ACT))
    crear_estructura()
    n = auto_etiquetar(modelo)
    if n > 0:
        augmentar()
    nuevo = entrenar()
    desplegar(nuevo)
    print("\n  COMPLETADO. Reinicia el servidor para activar el modelo mejorado.")

if __name__ == "__main__":
    main()
