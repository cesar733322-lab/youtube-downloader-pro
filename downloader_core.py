"""
Motor de descarga de YouTube a MP3 y Video (MP4) utilizando yt-dlp y ffmpeg.
Soporta:
- Extracción de playlists completas sin límite de videos.
- Compatibilidad para servidores en la nube (Render, Docker) evitando bloqueos de YouTube.
- Estimación precisa de tamaño (MB / GB) en tiempo real para MP3 y MP4.
- Descarga de audio (MP3 con bitrates: 128, 192, 256, 320 kbps).
- Descarga de video (MP4 con calidades: 360p, 480p, 720p, 1080p, Máxima disponible).
- Empaquetado directo en archivo ZIP para audios o videos.
- Unificación en UN SOLO AUDIO (.mp3) continuo en el orden de la playlist.
- Unificación en UN SOLO VIDEO (.mp4) continuo en el orden de la playlist.
- Previsualización rápida de miniaturas (portadas) sin descargar.
"""

import os
import sys
import re
import time
import zipfile
import shutil
import tempfile
import threading
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable, Any

import yt_dlp

# Configuración de opciones para yt-dlp
YTDLP_EXTRACTOR_ARGS = {}
YTDLP_JS_RUNTIMES = {'deno': {}, 'node': {}}

class DownloadCancelledError(Exception):
    """Excepción lanzada cuando el usuario cancela la descarga."""
    pass


def extract_video_id(url: str) -> Optional[str]:
    """Extrae el ID de 11 caracteres de un enlace de YouTube si existe."""
    m = re.search(r'(?:v=|\/|youtu\.be\/|^)([0-9A-Za-z_-]{11})(?:[?&]|$)', url.strip())
    if m:
        return m.group(1)
    return None


def format_duration(seconds: Optional[int | float]) -> str:
    """Convierte segundos a formato MM:SS o HH:MM:SS."""
    if not seconds or seconds <= 0:
        return "--:--"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def sanitize_filename(filename: str) -> str:
    """Limpia caracteres inválidos para nombres de archivo en Windows y Unix."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", filename)
    cleaned = cleaned.strip(". ")
    return cleaned if cleaned else "archivo"


def estimate_size(duration_sec: Optional[int | float], format_type: str = "mp3", quality: str = "192") -> Tuple[str, float]:
    """
    Calcula un peso estimado muy realista (en MB y texto legible) según la duración,
    el formato elegido (MP3 o MP4) y la calidad seleccionada.
    """
    if not duration_sec or duration_sec <= 0:
        duration_sec = 210

    fmt = format_type.lower()
    q = str(quality).lower()

    if "mp3" in fmt or "audio" in fmt:
        kbps = 192
        if "320" in q: kbps = 320
        elif "256" in q: kbps = 256
        elif "128" in q: kbps = 128
        bytes_total = duration_sec * (kbps * 1000 / 8)
    else:
        if "360" in q: kbps = 650
        elif "480" in q: kbps = 1250
        elif "720" in q: kbps = 2600
        elif "1080" in q: kbps = 5200
        else: kbps = 8500
        bytes_total = duration_sec * (kbps * 1000 / 8)

    mb = bytes_total / (1024 * 1024)
    if mb >= 1024:
        return f"~{mb / 1024:.2f} GB", mb
    return f"~{mb:.1f} MB", mb


def estimate_items_size(items: List[Any], format_type: str = "mp3", quality: str = "192") -> Tuple[str, float]:
    total_seconds = 0
    for item in items:
        if isinstance(item, dict):
            dur = item.get("duration") or 0
            total_seconds += (dur if dur > 0 else 210)
        else:
            total_seconds += 210
    return estimate_size(total_seconds, format_type, quality)


def fetch_image_bytes(url: str, timeout: int = 5) -> Optional[bytes]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def get_video_preview_info(url_or_id: str) -> Dict[str, Any]:
    url = url_or_id.strip()
    vid_id = extract_video_id(url)
    default_thumb = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg" if vid_id else ""

    if not url.startswith("http://") and not url.startswith("https://"):
        if vid_id:
            url = f"https://www.youtube.com/watch?v={vid_id}"

    ydl_opts = {
        'skip_download': True,
        'extract_flat': True,
        'js_runtimes': YTDLP_JS_RUNTIMES,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        info = None

    if not info:
        if vid_id:
            return {
                "id": vid_id,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "title": f"Video YouTube ({vid_id})",
                "channel": "YouTube",
                "duration": 210,
                "duration_str": "--:--",
                "thumbnail_url": default_thumb
            }
        raise ValueError("No se pudo obtener información del video.")

    v_id = info.get("id") or (vid_id or "")
    v_title = info.get("title") or "Video de YouTube"
    v_channel = info.get("channel") or info.get("uploader") or "Desconocido"
    v_duration = info.get("duration") or 0
    v_thumb = info.get("thumbnail") or default_thumb

    return {
        "id": v_id,
        "url": info.get("webpage_url") or f"https://www.youtube.com/watch?v={v_id}",
        "title": v_title,
        "channel": v_channel,
        "duration": v_duration,
        "duration_str": format_duration(v_duration),
        "thumbnail_url": v_thumb
    }


def extract_playlist_info(url_or_playlist: str) -> Dict[str, Any]:
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'js_runtimes': YTDLP_JS_RUNTIMES,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url_or_playlist, download=False)

    if not info:
        raise ValueError("No se pudo obtener información de la URL proporcionada.")

    title = info.get("title") or "Playlist de YouTube"
    uploader = info.get("uploader") or info.get("channel") or "Desconocido"

    raw_entries = info.get("entries")
    entries_list = []

    if raw_entries is not None:
        for idx, entry in enumerate(raw_entries):
            if not entry:
                continue
            v_id = entry.get("id") or ""
            v_title = entry.get("title") or f"Video {idx + 1}"
            v_duration = entry.get("duration") or 0
            v_channel = entry.get("channel") or entry.get("uploader") or uploader
            v_url = entry.get("url")
            if not v_url or not v_url.startswith("http"):
                v_url = f"https://www.youtube.com/watch?v={v_id}"

            v_thumb = ""
            thumbnails = entry.get("thumbnails")
            if thumbnails and isinstance(thumbnails, list) and len(thumbnails) > 0:
                v_thumb = thumbnails[-1].get("url", "")
            if not v_thumb and v_id:
                v_thumb = f"https://i.ytimg.com/vi/{v_id}/mqdefault.jpg"

            entries_list.append({
                "index": idx + 1,
                "id": v_id,
                "url": v_url,
                "title": v_title,
                "duration": v_duration,
                "duration_str": format_duration(v_duration),
                "channel": v_channel,
                "thumbnail_url": v_thumb
            })
    else:
        v_id = info.get("id") or ""
        v_title = info.get("title") or "Video de YouTube"
        v_duration = info.get("duration") or 0
        v_channel = info.get("channel") or info.get("uploader") or uploader
        v_url = info.get("webpage_url") or f"https://www.youtube.com/watch?v={v_id}"
        v_thumb = info.get("thumbnail") or (f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg" if v_id else "")

        entries_list.append({
            "index": 1,
            "id": v_id,
            "url": v_url,
            "title": v_title,
            "duration": v_duration,
            "duration_str": format_duration(v_duration),
            "channel": v_channel,
            "thumbnail_url": v_thumb
        })

    return {
        "title": title,
        "uploader": uploader,
        "total_count": len(entries_list),
        "entries": entries_list,
        "thumbnail_url": entries_list[0].get("thumbnail_url", "") if entries_list else ""
    }


def _get_video_format_string(quality: str) -> str:
    q = quality.lower()
    if "360" in q:
        return 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best'
    elif "480" in q:
        return 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best'
    elif "720" in q:
        return 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best'
    elif "1080" in q:
        return 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best'
    else:
        return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'


def download_audio(
    url_or_id: str,
    output_dir: str,
    bitrate: str = "192",
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> str:
    if cancel_event and cancel_event.is_set():
        raise DownloadCancelledError("Descarga cancelada.")

    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    def internal_hook(d):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelledError("Descarga cancelada por el usuario.")
        if progress_hook:
            progress_hook(d)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'js_runtimes': YTDLP_JS_RUNTIMES,
        'windowsfilenames': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': str(bitrate),
        }],
        'progress_hooks': [internal_hook],
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True
    }

    url = url_or_id
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://www.youtube.com/watch?v={url_or_id}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        req_dl = info.get("requested_downloads")
        if req_dl and len(req_dl) > 0 and req_dl[0].get("filepath"):
            final_path = req_dl[0]["filepath"]
            if os.path.exists(final_path):
                return final_path

        prep = ydl.prepare_filename(info)
        base, _ = os.path.splitext(prep)
        mp3_path = base + ".mp3"
        if os.path.exists(mp3_path):
            return mp3_path

        mp3_candidates = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.lower().endswith(".mp3")
        ]
        if mp3_candidates:
            mp3_candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            return mp3_candidates[0]

        raise FileNotFoundError(f"No se pudo encontrar el archivo MP3 generado para {url}")


def download_video(
    url_or_id: str,
    output_dir: str,
    quality: str = "720p",
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> str:
    if cancel_event and cancel_event.is_set():
        raise DownloadCancelledError("Descarga cancelada.")

    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    def internal_hook(d):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelledError("Descarga cancelada por el usuario.")
        if progress_hook:
            progress_hook(d)

    format_str = _get_video_format_string(quality)
    ydl_opts = {
        'format': format_str,
        'outtmpl': outtmpl,
        'js_runtimes': YTDLP_JS_RUNTIMES,
        'merge_output_format': 'mp4',
        'windowsfilenames': True,
        'progress_hooks': [internal_hook],
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True
    }

    url = url_or_id
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://www.youtube.com/watch?v={url_or_id}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        req_dl = info.get("requested_downloads")
        if req_dl and len(req_dl) > 0 and req_dl[0].get("filepath"):
            final_path = req_dl[0]["filepath"]
            if os.path.exists(final_path):
                return final_path

        prep = ydl.prepare_filename(info)
        base, _ = os.path.splitext(prep)
        mp4_path = base + ".mp4"
        if os.path.exists(mp4_path):
            return mp4_path

        candidates = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.lower().endswith(".mp4")
        ]
        if candidates:
            candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            return candidates[0]

        raise FileNotFoundError(f"No se pudo encontrar el archivo MP4 generado para {url}")


def _normalize_item(item: Any) -> Tuple[str, str]:
    if isinstance(item, dict):
        url = item.get("url") or f"https://www.youtube.com/watch?v={item.get('id', '')}"
        title = item.get("title") or url
        return url, title
    else:
        url = str(item).strip()
        return url, url


def download_batch_files(
    items: List[Any],
    output_dir: str,
    format_type: str = "mp3",
    quality: str = "192",
    max_workers: int = 3,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> Tuple[List[str], List[Tuple[str, str]]]:
    os.makedirs(output_dir, exist_ok=True)
    total = len(items)
    downloaded_files = []
    errors = []
    completed_lock = threading.Lock()
    completed_count = 0

    if cancel_event and cancel_event.is_set():
        return [], [("Todas", "Cancelado antes de iniciar")]

    is_mp4 = "mp4" in format_type.lower() or "video" in format_type.lower()

    def worker(item_data, item_index):
        nonlocal completed_count
        if cancel_event and cancel_event.is_set():
            return None, "Descarga cancelada"

        url, title = _normalize_item(item_data)

        if progress_callback:
            with completed_lock:
                progress_callback(completed_count, total, title, "Descargando")

        try:
            if is_mp4:
                res_file = download_video(
                    url_or_id=url,
                    output_dir=output_dir,
                    quality=quality,
                    cancel_event=cancel_event
                )
            else:
                res_file = download_audio(
                    url_or_id=url,
                    output_dir=output_dir,
                    bitrate=quality,
                    cancel_event=cancel_event
                )

            with completed_lock:
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total, title, "Completado")
            return res_file, None
        except Exception as e:
            with completed_lock:
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total, title, "Error")
            return None, (title, str(e))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, item, idx): idx for idx, item in enumerate(items)}
        for future in as_completed(futures):
            try:
                res_file, err = future.result()
                if res_file:
                    downloaded_files.append(res_file)
                if err and isinstance(err, tuple):
                    errors.append(err)
            except Exception as e:
                errors.append(("Item", str(e)))

    return downloaded_files, errors


download_batch = lambda items, output_dir, bitrate="192", max_workers=3, progress_callback=None, cancel_event=None: download_batch_files(
    items, output_dir, format_type="mp3", quality=bitrate, max_workers=max_workers, progress_callback=progress_callback, cancel_event=cancel_event
)


def download_batch_and_zip(
    items: List[Any],
    output_dir: str,
    zip_filename: Optional[str] = None,
    format_type: str = "mp3",
    quality: str = "192",
    bitrate: Optional[str] = None,
    max_workers: int = 3,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    keep_individual: bool = False
) -> Tuple[str, List[str], List[Tuple[str, str]]]:
    os.makedirs(output_dir, exist_ok=True)
    if bitrate:
        quality = bitrate

    ext_desc = "Videos" if "mp4" in format_type.lower() else "MP3s"
    if not zip_filename:
        zip_filename = f"YouTube_{ext_desc}_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    if not zip_filename.lower().endswith(".zip"):
        zip_filename += ".zip"

    zip_path = os.path.join(output_dir, zip_filename)
    temp_dir = tempfile.mkdtemp(prefix="yt_dl_zip_", dir=output_dir)

    try:
        downloaded_files, errors = download_batch_files(
            items=items,
            output_dir=temp_dir,
            format_type=format_type,
            quality=quality,
            max_workers=max_workers,
            progress_callback=progress_callback,
            cancel_event=cancel_event
        )

        if cancel_event and cancel_event.is_set():
            return "", [], errors

        if not downloaded_files:
            raise RuntimeError("No se pudo descargar ningún archivo exitosamente para generar el ZIP.")

        if progress_callback:
            progress_callback(len(items), len(items), "Empaquetando en ZIP", "Comprimiendo")

        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
            for file_path in downloaded_files:
                if os.path.exists(file_path):
                    arcname = os.path.basename(file_path)
                    zipf.write(file_path, arcname=arcname)
                    if keep_individual:
                        dest = os.path.join(output_dir, arcname)
                        shutil.copy2(file_path, dest)

        return zip_path, downloaded_files, errors

    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def download_and_merge_audios(
    items: List[Any],
    output_dir: str,
    output_filename: Optional[str] = None,
    bitrate: str = "192",
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> Tuple[str, List[Tuple[str, str]]]:
    os.makedirs(output_dir, exist_ok=True)
    if not output_filename:
        output_filename = f"Audio_Unido_{time.strftime('%Y%m%d_%H%M%S')}.mp3"
    if not output_filename.lower().endswith(".mp3"):
        output_filename += ".mp3"

    final_audio_path = os.path.join(output_dir, output_filename)
    temp_dir = tempfile.mkdtemp(prefix="yt_merge_audio_", dir=output_dir)

    total = len(items)
    ordered_files = []
    errors = []

    try:
        for idx, item in enumerate(items):
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelledError("Operación cancelada por el usuario.")

            url, title = _normalize_item(item)
            if progress_callback:
                progress_callback(idx, total, title, f"Descargando audio ({idx+1}/{total})")

            part_name = f"part_{idx:04d}.%(ext)s"
            part_outtmpl = os.path.join(temp_dir, part_name)

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': part_outtmpl,
                'js_runtimes': YTDLP_JS_RUNTIMES,
                'windowsfilenames': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': str(bitrate),
                }],
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    expected_mp3 = os.path.join(temp_dir, f"part_{idx:04d}.mp3")
                    if os.path.exists(expected_mp3):
                        ordered_files.append(expected_mp3)
                    else:
                        candidates = [
                            os.path.join(temp_dir, f)
                            for f in os.listdir(temp_dir)
                            if f.startswith(f"part_{idx:04d}.") and f.endswith(".mp3")
                        ]
                        if candidates:
                            ordered_files.append(candidates[0])
                        else:
                            raise FileNotFoundError(f"No se generó el audio para {title}")
            except Exception as e:
                errors.append((title, str(e)))

        if cancel_event and cancel_event.is_set():
            raise DownloadCancelledError("Cancelado por el usuario.")

        if not ordered_files:
            raise RuntimeError("No se pudo descargar ningún audio para unir.")

        if progress_callback:
            progress_callback(total, total, "Uniendo audios con FFmpeg", "Finalizando")

        concat_list_file = os.path.join(temp_dir, "concat_audio.txt")
        with open(concat_list_file, "w", encoding="utf-8") as f_list:
            for part in ordered_files:
                clean_path = os.path.abspath(part).replace("\\", "/")
                f_list.write(f"file '{clean_path}'\n")

        merge_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_file,
            "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
            final_audio_path
        ]
        subprocess.run(merge_cmd, capture_output=True, check=True)

        return final_audio_path, errors

    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def download_and_merge_videos(
    items: List[Any],
    output_dir: str,
    output_filename: Optional[str] = None,
    quality: str = "720p",
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> Tuple[str, List[Tuple[str, str]]]:
    os.makedirs(output_dir, exist_ok=True)
    if not output_filename:
        output_filename = f"Video_Unido_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    if not output_filename.lower().endswith(".mp4"):
        output_filename += ".mp4"

    final_video_path = os.path.join(output_dir, output_filename)
    temp_dir = tempfile.mkdtemp(prefix="yt_merge_vid_", dir=output_dir)

    total = len(items)
    normalized_parts = []
    errors = []

    try:
        for idx, item in enumerate(items):
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelledError("Operación cancelada por el usuario.")

            url, title = _normalize_item(item)
            if progress_callback:
                progress_callback(idx, total, title, f"Descargando video ({idx+1}/{total})")

            raw_vid_outtmpl = os.path.join(temp_dir, f"raw_{idx:04d}.%(ext)s")
            ydl_opts = {
                'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
                'outtmpl': raw_vid_outtmpl,
                'js_runtimes': YTDLP_JS_RUNTIMES,
                'windowsfilenames': True,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True
            }

            downloaded_raw_file = None
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    req_dl = info.get("requested_downloads")
                    if req_dl and req_dl[0].get("filepath"):
                        downloaded_raw_file = req_dl[0]["filepath"]
                    else:
                        prep = ydl.prepare_filename(info)
                        if os.path.exists(prep):
                            downloaded_raw_file = prep
                        else:
                            for f in os.listdir(temp_dir):
                                if f.startswith(f"raw_{idx:04d}."):
                                    downloaded_raw_file = os.path.join(temp_dir, f)
                                    break

                if not downloaded_raw_file or not os.path.exists(downloaded_raw_file):
                    raise FileNotFoundError(f"No se pudo descargar el video {title}")

                if progress_callback:
                    progress_callback(idx, total, title, f"Procesando clip ({idx+1}/{total})")

                part_ts = os.path.join(temp_dir, f"part_{idx:04d}.ts")
                norm_cmd = [
                    "ffmpeg", "-y", "-i", downloaded_raw_file,
                    "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                    part_ts
                ]
                subprocess.run(norm_cmd, capture_output=True, check=True)

                if os.path.exists(part_ts):
                    normalized_parts.append(part_ts)

                try:
                    os.remove(downloaded_raw_file)
                except Exception:
                    pass

            except Exception as e:
                errors.append((title, str(e)))

        if cancel_event and cancel_event.is_set():
            raise DownloadCancelledError("Cancelado por el usuario.")

        if not normalized_parts:
            raise RuntimeError("No se pudo procesar ningún video para unir.")

        if progress_callback:
            progress_callback(total, total, "Uniendo videos con FFmpeg", "Finalizando")

        concat_list_file = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list_file, "w", encoding="utf-8") as f_list:
            for part in normalized_parts:
                clean_path = os.path.abspath(part).replace("\\", "/")
                f_list.write(f"file '{clean_path}'\n")

        merge_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_file,
            "-c", "copy",
            final_video_path
        ]
        subprocess.run(merge_cmd, capture_output=True, check=True)

        return final_video_path, errors

    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
