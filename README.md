# 🎬 YouTube Downloader Pro (Desktop & Web/Móvil)

Una potente aplicación de escritorio y aplicación web móvil moderna para descargar audios (MP3) y videos (MP4) de YouTube, por enlaces individuales, por lotes o desde **playlists completas sin ningún límite de videos**, con cálculo de peso en MB/GB, portadas en tiempo real y opciones para unir archivos.

---

## 🌟 Opciones de Alojamiento y Uso desde el Celular

### ⚠️ ¿Por qué Hugging Face ya no es gratis para esto?
Como viste en tu pantalla, Hugging Face **recientemente bloqueó Gradio y Docker en cuentas gratuitas** (ahora tienen el candado 🔒 **Paid** y exigen suscripción PRO). Solo permiten "Static" (archivos HTML planos sin procesamiento de servidor ni Python/FFmpeg).

---

### 🏆 Las 3 Mejores Alternativas 100% Gratuitas para la Nube y Móvil:

#### 1. 🌐 Opción 1: Render.com (En la Nube 100% Gratis)
Render.com sigue ofreciendo un plan **Free** para desplegar contenedores **Docker** con Python y FFmpeg:
1. Sube tu carpeta a un repositorio en **GitHub** (puede ser público o privado).
2. Entra en [Render.com](https://render.com) e inicia sesión con tu cuenta de GitHub.
3. Haz clic en **New +** > **Web Service**.
4. Conecta tu repositorio de GitHub.
5. Render detectará automáticamente el archivo [Dockerfile](file:///e:/Escritorio/Descargador%20de%20videos%20Youtube/Dockerfile) que ya te dejé preparado.
6. En **Instance Type**, selecciona **Free**.
7. Haz clic en **Create Web Service**. ¡Te dará un enlace web público tipo `https://tu-app.onrender.com` gratis para siempre!

---

#### 2. ⚡ Opción 2: Tu PC + Enlace Seguro HTTPS para el Celular (¡La más rápida y sin bloqueos!)
Si quieres abrir la app en tu celular estés donde estés (en la calle con 4G/5G o en cualquier lugar):
1. Haz doble clic en el archivo:
   ```text
   Iniciar_Tunel_Internet.bat
   ```
2. Te generará automáticamente un enlace seguro HTTPS gratuito de Cloudflare (ejemplo: `https://palabras-aleatorias.trycloudflare.com`).
3. Abres ese enlace en el navegador de tu celular y tendrás acceso completo a toda la app web con la máxima velocidad de tu computadora y sin que YouTube te ponga captchas de robot.

---

#### 3. ☁️ Opción 3: Google Colab (En la Nube de Google en 1 Clic)
Puedes abrir el archivo [Colab_Youtube_Downloader.ipynb](file:///e:/Escritorio/Descargador%20de%20videos%20Youtube/Colab_Youtube_Downloader.ipynb) directamente en [Google Colab](https://colab.research.google.com/):
- Ejecutas la celda y Google iniciará el servidor en sus servidores en la nube dándote un enlace web directo para tu celular.

---

## 💻 Uso en tu Computadora (Escritorio)

Para abrir la aplicación de escritorio moderna con todas las funciones:
```text
Iniciar_Descargador.bat
```
*(O desde la terminal ejecutando `py main.py`)*.
