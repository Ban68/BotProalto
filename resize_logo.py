from PIL import Image
import os

input_path = r"C:\Users\carlo\OneDrive\Marca\LOGO ProAlto Profile-02.jpg"
output_path = r"C:\Users\carlo\OneDrive\Marca\LOGO ProAlto Profile-WhatsApp.jpg"

img = Image.open(input_path)
img = img.resize((640, 640), Image.LANCZOS)
img.save(output_path, "JPEG", quality=95)

print(f"✅ Imagen guardada en: {output_path}")
print(f"   Tamaño: {img.size[0]}x{img.size[1]} px")
print(f"   Archivo: {os.path.getsize(output_path) / 1024:.1f} KB")
