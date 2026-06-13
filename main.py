
import asyncio
import os
from collections import defaultdict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request

from agent import run_agent
from database import init_db, seed_db
from memory import memory
from whatsapp import extract_incoming, send_reply

load_dotenv()

BUFFER_SECONDS = float(os.getenv("BUFFER_SECONDS", "8"))

buffers: dict[str, list[str]] = defaultdict(list)
buffer_tasks: dict[str, asyncio.Task] = {}
locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_db()
    print(f"Engine siap. Buffer debounce: {BUFFER_SECONDS}s")
    yield



app = FastAPI(title="Glowria AI Sales Agent", lifespan=lifespan)



async def process_buffered_messages(phone: str) -> None:
    """Dipanggil saat timer debounce habis: proses semua pesan di buffer."""
    await asyncio.sleep(BUFFER_SECONDS)  # <- di-cancel kalau ada pesan baru

    async with locks[phone]:
        pending = buffers.pop(phone, [])
        if not pending:
            return
        combined = "\n".join(pending)
        print(f"[buffer] {phone}: {len(pending)} pesan digabung -> {combined!r}")

        # SAKLAR TAKEOVER: admin sedang pegang chat ini? AI diam total.
        if not memory.is_ai_enabled(phone):
            print(f"[takeover] AI nonaktif untuk {phone}, pesan disimpan saja.")
            memory.add(phone, "user", combined)
            return

        history = memory.get_history(phone)

        # run_agent itu blocking (sync) -> jalankan di thread supaya
        # event loop tetap bisa menerima webhook nomor lain.
        try:
            reply, _ = await asyncio.to_thread(run_agent, history, combined, phone)
        except Exception as e:
            print(f"[error] gagal proses {phone}: {e}")
            return

        memory.add(phone, "user", combined)
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

    phone, text = incoming["phone"], incoming["text"]
    print(f"[masuk] {phone} ({incoming.get('name')}): {text!r}")

    buffers[phone].append(text)
    schedule_processing(phone)
    return {"status": "buffered", "pending": len(buffers[phone])}


@app.get("/health")
async def health():
    """Untuk monitoring/uptime check di Railway atau VPS."""
    return {"status": "ok", "buffer_seconds": BUFFER_SECONDS}
