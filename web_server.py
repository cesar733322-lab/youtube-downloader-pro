"""
Servidor Web Flask para YouTube Downloader Pro.
Permite utilizar todas las funciones desde cualquier navegador (PC, Tablet, iPhone, Android).
"""

import os
import sys
import socket
import tempfile
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory

import downloader_core

app = Flask(__name__, static_folder="web")

def get_local_ip():
    """Detecta la IP local de la computadora en la red Wi-Fi."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/preview", methods=["POST"])
def api_preview():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No se proporcionó URL"}), 400
    try:
        info = downloader_core.get_video_preview_info(url)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/playlist", methods=["POST"])
def api_playlist():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No se proporcionó URL"}), 400
    try:
        info = downloader_core.extract_playlist_info(url)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json() or {}
    urls = data.get("urls", [])
    fmt = data.get("format", "mp3")
    quality = data.get("quality", "192")
    as_zip = data.get("asZip", False)

    if not urls:
        return jsonify({"error": "Lista de URLs vacía"}), 400

    temp_dir = tempfile.mkdtemp(prefix="web_dl_")
    try:
        if as_zip or len(urls) > 1:
            zip_name = f"Descarga_{int(time.time())}.zip"
            zip_path, files, errs = downloader_core.download_batch_and_zip(
                items=urls,
                output_dir=temp_dir,
                zip_filename=zip_name,
                format_type=fmt,
                quality=quality
            )
            return send_file(zip_path, as_attachment=True, download_name=zip_name)
        else:
            # Archivo único directo
            url = urls[0]
            if "video" in fmt or "mp4" in fmt:
                file_path = downloader_core.download_video(url, temp_dir, quality=quality)
            else:
                file_path = downloader_core.download_audio(url, temp_dir, bitrate=quality)
            return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download/zip", methods=["POST"])
def api_download_zip():
    data = request.get_json() or {}
    items = data.get("items", [])
    fmt = data.get("format", "mp3")
    quality = data.get("quality", "192")

    if not items:
        return jsonify({"error": "Sin elementos seleccionados"}), 400

    temp_dir = tempfile.mkdtemp(prefix="web_pl_zip_")
    try:
        zip_name = f"Playlist_{int(time.time())}.zip"
        zip_path, files, errs = downloader_core.download_batch_and_zip(
            items=items,
            output_dir=temp_dir,
            zip_filename=zip_name,
            format_type=fmt,
            quality=quality
        )
        return send_file(zip_path, as_attachment=True, download_name=zip_name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/merge/audio", methods=["POST"])
def api_merge_audio():
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "Sin elementos seleccionados"}), 400

    temp_dir = tempfile.mkdtemp(prefix="web_merge_a_")
    try:
        audio_name = f"Playlist_AudioCompleto_{int(time.time())}.mp3"
        final_path, errors = downloader_core.download_and_merge_audios(
            items=items,
            output_dir=temp_dir,
            output_filename=audio_name
        )
        return send_file(final_path, as_attachment=True, download_name=audio_name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/merge/video", methods=["POST"])
def api_merge_video():
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "Sin elementos seleccionados"}), 400

    temp_dir = tempfile.mkdtemp(prefix="web_merge_v_")
    try:
        video_name = f"Playlist_VideoCompleto_{int(time.time())}.mp4"
        final_path, errors = downloader_core.download_and_merge_videos(
            items=items,
            output_dir=temp_dir,
            output_filename=video_name
        )
        return send_file(final_path, as_attachment=True, download_name=video_name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    local_ip = get_local_ip()
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 65)
    print("      🚀 SERVIDOR WEB YOUTUBE DOWNLOADER PRO INICIADO")
    print("=" * 65)
    print(f"  💻 En esta PC:       http://localhost:{port}")
    print(f"  📱 En tu CELULAR:    http://{local_ip}:{port}")
    print("  (Asegúrate de que tu celular esté conectado a la misma red Wi-Fi)")
    print("=" * 65 + "\n")

    app.run(host="0.0.0.0", port=port, debug=False)
