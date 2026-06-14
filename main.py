
import asyncio
import os
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from agent import run_agent
from database import init_db, seed_db
from memory import memory
from routes.dashboard import router as dashboard_router
from whatsapp import extract_incoming, fetch_media_b64, send_reply

load_dotenv()

BUFFER_SECONDS = float(os.getenv("BUFFER_SECONDS", "8"))

# Folder simpan gambar customer (fallback lokal saat R2 belum dikonfigurasi).
MEDIA_DIR = Path(__file__).parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)

# ---- Cloudflare R2 / S3 (opsional) -----------------------------------------
# Kalau R2_BUCKET kosong -> simpan ke disk lokal. Kalau diisi -> upload ke R2.
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").rstrip("/")

# R2 hanya aktif kalau SEMUA nilai terisi; kalau belum -> fallback lokal (aman).
R2_ENABLED = all([R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_URL])

EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_s3 = None


def _get_s3():
    """Lazy init klien S3 (boto3 hanya di-import kalau R2 dipakai)."""
    global _s3
    if _s3 is None:
        import boto3
        _s3 = boto3.client(
            "s3", endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
    return _s3


def save_media(phone: str, data: bytes, mime: str) -> str:
    """Simpan byte gambar, kembalikan path relatif 'media/<file>'.

    Penyimpanan: R2 (kalau aktif) atau disk lokal. Penyajian: SELALU lewat
    route /media/<file> di app (lihat fungsi media()), bukan URL R2 langsung.
    """
    fname = f"{phone}_{uuid.uuid4().hex[:8]}.{EXT.get(mime, 'jpg')}"
    if R2_ENABLED:
        _get_s3().put_object(Bucket=R2_BUCKET, Key=fname, Body=data, ContentType=mime)
    else:
        (MEDIA_DIR / fname).write_bytes(data)
    return f"media/{fname}"   # selalu disajikan lewat /media/<file> (proxy app)


# Tiap item buffer adalah dict dari extract_incoming (teks dan/atau gambar).
buffers: dict[str, list[dict]] = defaultdict(list)
buffer_tasks: dict[str, asyncio.Task] = {}
locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_db()
    print(f"Engine siap. Buffer debounce: {BUFFER_SECONDS}s")
    yield



app = FastAPI(title="Glowria AI Sales Agent", lifespan=lifespan)

# Dashboard (Day 2): router
app.include_router(dashboard_router)


@app.get("/")
def root():
    """Buka domain langsung (localhost/Railway) -> arahkan ke dashboard."""
    return RedirectResponse(url="/dashboard")


@app.get("/media/{fname}")
def media(fname: str):
    """Sajikan gambar lewat domain app (proxy): ambil dari R2 kalau aktif, else disk.

    Browser tidak pernah menyentuh domain R2 publik (r2.dev) -> kebal blokir/
    intersepsi TLS di jaringan tertentu. Server (Railway) yang ambil dari R2.
    """
    fname = os.path.basename(fname)                       # cegah path traversal
    headers = {"Cache-Control": "public, max-age=86400"}
    if R2_ENABLED:
        try:
            obj = _get_s3().get_object(Bucket=R2_BUCKET, Key=fname)
        except Exception:
            raise HTTPException(status_code=404, detail="Gambar tidak ditemukan.")
        return Response(content=obj["Body"].read(),
                        media_type=obj.get("ContentType", "image/jpeg"), headers=headers)
    fpath = MEDIA_DIR / fname
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Gambar tidak ditemukan.")
    return FileResponse(fpath, headers=headers)



async def process_buffered_messages(phone: str) -> None:
    """Dipanggil saat timer debounce habis: proses semua pesan di buffer."""
    await asyncio.sleep(BUFFER_SECONDS)  # <- di-cancel kalau ada pesan baru

    async with locks[phone]:
        pending = buffers.pop(phone, [])
        if not pending:
            return

        # Simpan nama WhatsApp customer (pushName) -> tampil di dashboard
        name = next((i.get("name") for i in reversed(pending) if i.get("name")), None)
        if name:
            memory.set_name(phone, name)

        # Gabung teks + ambil & simpan gambar (decrypt base64 via Evolution).
        texts: list[str] = []
        images: list[tuple[bytes, str]] = []
        memory_lines: list[str] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for item in pending:
                if item.get("text"):
                    texts.append(item["text"])
                if item.get("media_type") == "image":
                    fetched = await fetch_media_b64(client, item["message"])
                    if fetched:
                        img_bytes, mime = fetched
                        path = save_media(phone, img_bytes, mime)
                        images.append((img_bytes, mime))
                        memory_lines.append(f"[image:{path}]")  # ditandai untuk dashboard

        combined = "\n".join(texts)
        # Teks yang disimpan ke memory/dashboard: caption + penanda gambar.
        memory_text = "\n".join([combined] + memory_lines).strip() or "[customer mengirim gambar]"
        print(f"[buffer] {phone}: {len(pending)} pesan, {len(images)} gambar -> {memory_text!r}")

        # SAKLAR TAKEOVER: admin sedang pegang chat ini? AI diam total.
        if not memory.is_ai_enabled(phone):
            print(f"[takeover] AI nonaktif untuk {phone}, pesan disimpan saja.")
            memory.add(phone, "user", memory_text)
            return

        history = memory.get_history(phone)

        # run_agent itu blocking (sync) -> jalankan di thread supaya
        # event loop tetap bisa menerima webhook nomor lain.
        try:
            reply, _ = await asyncio.to_thread(run_agent, history, combined, phone, images)
        except Exception as e:
            print(f"[error] gagal proses {phone}: {e}")
            return

        memory.add(phone, "user", memory_text)
        memory.add(phone, "model", reply)

        # DETEKSI [HANDOVER]: matikan AI untuk nomor ini sebelum membalas.
        # (Literal string di output AI, sesuai HARD RULE 15 di system prompt.)
        if "[HANDOVER]" in reply:
            memory.set_ai_enabled(phone, False)
            print(f"[handover] AI dinonaktifkan untuk {phone}. "
                "Notifikasi admin dikirim (production: WA grup admin/dashboard).")

        await send_reply(phone, reply)
        print(f"[balas] {phone}: {reply!r}")


def schedule_processing(phone: str) -> None:
    """Reset timer debounce untuk nomor ini."""
    old_task = buffer_tasks.get(phone)
    if old_task and not old_task.done():
        old_task.cancel()
    buffer_tasks[phone] = asyncio.create_task(process_buffered_messages(phone))



@app.post("/webhook")
async def webhook(request: Request):
    """Penerima event Evolution API. HARUS balas cepat (<1 detik):
    proses berat terjadi di background task, bukan di handler ini."""
    payload = await request.json()

    incoming = extract_incoming(payload)
    if incoming is None:
        return {"status": "ignored"}

    phone = incoming["phone"]
    tag = " +gambar" if incoming.get("media_type") == "image" else ""
    print(f"[masuk] {phone} ({incoming.get('name')}): {incoming['text']!r}{tag}")

    buffers[phone].append(incoming)
    schedule_processing(phone)
    return {"status": "buffered", "pending": len(buffers[phone])}


@app.get("/health")
async def health():
    """Untuk monitoring/uptime check di Railway atau VPS."""
    return {"status": "ok", "buffer_seconds": BUFFER_SECONDS}
