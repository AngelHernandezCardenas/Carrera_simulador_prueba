import sys
sys.path.insert(0, '.')
from Puntaje import refrescar_puntajes_retos, activity_points_cache

result = refrescar_puntajes_retos()
print("Challenge points per team:")
for k, v in sorted(result.items()):
    pts = activity_points_cache.get(k, "N/A")
    print(f"  {k}: challenges={pts}")
