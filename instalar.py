import os
import sys
import subprocess
import platform

def run_command(command, cwd=None):
    print(f"\n Ejecutando: {' '.join(command)}")
    try:
        # Usar shell=True en Windows para comandos como 'npm'
        use_shell = platform.system() == "Windows"
        subprocess.check_call(command, cwd=cwd, shell=use_shell)
        print(" Completado con éxito.")
    except subprocess.CalledProcessError as e:
        print(f" Error al ejecutar el comando. Código de salida: {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"No se encontró el comando '{command[0]}'. Asegúrate de tenerlo instalado.")
        sys.exit(1)

def main():
    print("====================================================")
    print("  Instalador de Dependencias Multiplataforma")
    print("  Compatible con Windows, macOS y Linux")
    print("====================================================\n")

    base_dir = os.path.abspath(os.path.dirname(__file__))

    # 1. Instalar dependencias de Python (Backend)
    req_file = os.path.join(base_dir, "requirements.txt")
    if os.path.exists(req_file):
        print(" Instalando dependencias de Python (Backend)...")
        # sys.executable asegura que usemos el mismo entorno de Python (ej. si está en un entorno virtual)
        run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=base_dir)
    else:
        print("No se encontró requirements.txt. Saltando dependencias de Python.")

    # 2. Instalar dependencias de Node.js (Frontend - RelieVeasy)
    frontend_dir = os.path.join(base_dir, "RelieVeasy")
    if os.path.exists(frontend_dir) and os.path.exists(os.path.join(frontend_dir, "package.json")):
        print("\nInstalando dependencias de Node.js (Frontend Next.js)...")
        # En Windows 'npm' suele ser 'npm.cmd' cuando se llama desde subprocess sin shell=True, 
        # pero run_command ya maneja shell=True para Windows.
        npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"
        run_command([npm_cmd, "install"], cwd=frontend_dir)
    else:
        print("\n No se encontró la carpeta 'RelieVeasy' o su 'package.json'. Saltando dependencias de Frontend.")

    print("\n ¡Todas las dependencias se instalaron correctamente!")
    print(" Puedes subir todo esto a GitHub y ejecutar este archivo en cualquier computadora con: python instalar.py")

if __name__ == "__main__":
    main()
