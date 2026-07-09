import re

file_path = "c:/Users/jrhe0/Downloads/Carrera_simulador_prueba-optimizacion-y-organizacion/Carrera_simulador_prueba-optimizacion-y-organizacion/tracker-app/App.js"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Extract the block
match_server = re.search(r"(\s*\{\/\*\s*SERVER AND REGISTRATION\s*\*\/\}[\s\S]*?<\/View>)\s*\{\/\*\s*METRICS\s*\*\/\}", content)
# wait, the METRICS block is BEFORE SERVER AND REGISTRATION.
match_server = re.search(r"(\s*\{\/\*\s*SERVER AND REGISTRATION\s*\*\/\}[\s\S]*?<\/View>)\s*(?:\{\/\*\s*METRICS\s*\*\/\}|\{\!isScannerMode && \()", content)

# A better way is to split on EXACT strings.
start_str = "      {/* SERVER AND REGISTRATION */}"
end_str_after = "      {!isScannerMode && ("

start_idx = content.find(start_str)
end_idx = content.find(end_str_after, start_idx)
if start_idx != -1 and end_idx != -1:
    block = content[start_idx:end_idx]
    
    # Remove it from current place
    content = content[:start_idx] + content[end_idx:]
    
    # Insert it before {/* CAMERA AND YOLO */}
    insert_point = content.find("      {/* CAMERA AND YOLO */}")
    if insert_point != -1:
        content = content[:insert_point] + block + content[insert_point:]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("Success")
    else:
        print("Insert point not found")
else:
    print("Block not found")
