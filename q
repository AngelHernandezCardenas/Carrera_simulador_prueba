[1mdiff --git a/.gitattributes b/.gitattributes[m
[1mdeleted file mode 100644[m
[1mindex dfe0770..0000000[m
[1m--- a/.gitattributes[m
[1m+++ /dev/null[m
[36m@@ -1,2 +0,0 @@[m
[31m-# Auto detect text files and perform LF normalization[m
[31m-* text=auto[m
[1mdiff --git a/app.py b/app.py[m
[1mindex 50e4f1c..abf2703 100644[m
[1m--- a/app.py[m
[1m+++ b/app.py[m
[36m@@ -123,17 +123,12 @@[m [mdef gps():[m
             "speed_kmh":           data.get("speed_kmh"),[m
             "speed_source":        data.get("speed_source"),[m
 [m
[31m-            # Acelerómetro sin gravedad[m
[31m-            "accel_x":             data.get("accel_x"),[m
[31m-            "accel_y":             data.get("accel_y"),[m
[31m-            "accel_z":             data.get("accel_z"),[m
[31m-            "accel_magnitude":     data.get("accel_magnitude"),[m
[31m-[m
             # Acelerómetro con gravedad[m
             "accel_gx":            data.get("accel_gx"),[m
             "accel_gy":            data.get("accel_gy"),[m
             "accel_gz":            data.get("accel_gz"),[m
             "accel_g_magnitude":   data.get("accel_g_magnitude"),[m
[32m+[m[32m            "acceleration_mps2":   data.get("acceleration_mps2"),[m
 [m
             # Metadatos del sensor[m
             "accel_interval_ms":       data.get("accel_interval_ms"),[m
[36m@@ -157,7 +152,7 @@[m [mdef gps():[m
         f"[GPS] {participante} {feature['properties']['device_label']} "[m
         f"{data['latitude']}, {data['longitude']} "[m
         f"vel={data.get('speed_kmh', 'N/A')} km/h ({data.get('speed_source', '')}) "[m
[31m-        f"accel=({data.get('accel_x', '-')}, {data.get('accel_y', '-')}, {data.get('accel_z', '-')}) "[m
[32m+[m[32m        f"accel={data.get('acceleration_mps2', '-')} m/s2 "[m
         f"(+/-{data.get('accuracy', '')}m)"[m
     )[m
 [m
[1mdiff --git a/templates/index.html b/templates/index.html[m
[1mindex 23889d2..2297239 100644[m
[1m--- a/templates/index.html[m
[1m+++ b/templates/index.html[m
[36m@@ -80,19 +80,17 @@[m
         </div>[m
 [m
         <div class="card full">[m
[31m-            <div class="label">Acelerómetro sin gravedad</div>[m
[31m-            <div class="small" id="acel">X: --[m
[32m+[m[32m            <div class="label">Acelerómetro con gravedad</div>[m
[32m+[m[32m            <div class="small" id="acelG">X: --[m
 Y: --[m
 Z: --[m
 Magnitud: --</div>[m
         </div>[m
 [m
         <div class="card full">[m
[31m-            <div class="label">Acelerómetro con gravedad</div>[m
[31m-            <div class="small" id="acelG">X: --[m
[31m-Y: --[m
[31m-Z: --[m
[31m-Magnitud: --</div>[m
[32m+[m[32m            <div class="label">Aceleración</div>[m
[32m+[m[32m            <div class="value" id="aceleracionReal">-- m/s²</div>[m
[32m+[m[32m            <div class="small">Sensor del teléfono</div>[m
         </div>[m
     </div>[m
 [m
[36m@@ -107,8 +105,8 @@[m [mMagnitud: --</div>[m
     const DEVICE_ID_KEY = "gps_tracker_device_id";[m
 [m
     let accelData = {[m
[31m-        x: null, y: null, z: null, magnitude: null,[m
         gx: null, gy: null, gz: null, g_magnitude: null,[m
[32m+[m[32m        acceleration_mps2: null,[m
         interval_ms: null,[m
         sensor_timestamp_ms: null,[m
         supported: false,[m
[36m@@ -150,32 +148,24 @@[m [mMagnitud: --</div>[m
     // -------------------------------------------------------------------------[m
 [m
     function actualizarPanelAcelerometro() {[m
[31m-        document.getElementById("acel").textContent =[m
[31m-            `X: ${fmt(accelData.x, 3)} m/s²\n` +[m
[31m-            `Y: ${fmt(accelData.y, 3)} m/s²\n` +[m
[31m-            `Z: ${fmt(accelData.z, 3)} m/s²\n` +[m
[31m-            `Magnitud: ${fmt(accelData.magnitude, 3)} m/s²`;[m
[31m-[m
         document.getElementById("acelG").textContent =[m
             `X: ${fmt(accelData.gx, 3)} m/s²\n` +[m
             `Y: ${fmt(accelData.gy, 3)} m/s²\n` +[m
             `Z: ${fmt(accelData.gz, 3)} m/s²\n` +[m
             `Magnitud: ${fmt(accelData.g_magnitude, 3)} m/s²`;[m
[32m+[m
[32m+[m[32m        document.getElementById("aceleracionReal").textContent =[m
[32m+[m[32m            `${fmt(accelData.acceleration_mps2, 3)} m/s²`;[m
     }[m
 [m
     function onDeviceMotion(event) {[m
[31m-        const a  = event.acceleration || {};[m
         const ag = event.accelerationIncludingGravity || {};[m
 [m
[31m-        accelData.x         = numOrNull(a.x);[m
[31m-        accelData.y         = numOrNull(a.y);[m
[31m-        accelData.z         = numOrNull(a.z);[m
[31m-        accelData.magnitude = calcularMagnitud(accelData.x, accelData.y, accelData.z);[m
[31m-[m
         accelData.gx          = numOrNull(ag.x);[m
         accelData.gy          = numOrNull(ag.y);[m
         accelData.gz          = numOrNull(ag.z);[m
         accelData.g_magnitude = calcularMagnitud(accelData.gx, accelData.gy, accelData.gz);[m
[32m+[m[32m        accelData.acceleration_mps2 = accelData.g_magnitude;[m
 [m
         accelData.interval_ms         = numOrNull(event.interval);[m
         accelData.sensor_timestamp_ms = Date.now();[m
[36m@@ -376,15 +366,11 @@[m [mMagnitud: --</div>[m
                             speed_kmh:    speed.speed_kmh,[m
                             speed_source: speed.speed_source,[m
 [m
[31m-                            accel_x:         accelData.x,[m
[31m-                            accel_y:         accelData.y,[m
[31m-                            accel_z:         accelData.z,[m
[31m-                            accel_magnitude: accelData.magnitude,[m
[31m-[m
                             accel_gx:          accelData.gx,[m
                             accel_gy:          accelData.gy,[m
                             accel_gz:          accelData.gz,[m
                             accel_g_magnitude: accelData.g_magnitude,[m
[32m+[m[32m                            acceleration_mps2: accelData.acceleration_mps2,[m
 [m
                             accel_interval_ms:       accelData.interval_ms,[m
                             accel_supported:         accelData.supported,[m
