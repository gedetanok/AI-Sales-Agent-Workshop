import asyncio
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip("/")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "glowria")

HEADERS = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

TYPING_SECONDS_PER_CHAR = 0.03   # ~33 karakter/detik
TYPING_MIN_SECONDS = 1.0
TYPING_MAX_SECONDS = 5.0


def _typing_duration(text: str) -> float:
    return min(max(len(text) * TYPING_SECONDS_PER_CHAR, TYPING_MIN_SECONDS), TYPING_MAX_SECONDS)


async def send_typing(client: httpx.AsyncClient, phone: str, seconds: float) -> None:
    """Tampilkan 'sedang mengetik...' di sisi customer."""
    try:
        await client.post(
            f"{EVOLUTION_API_URL}/chat/sendPresence/{EVOLUTION_INSTANCE}",
            headers=HEADERS,
            json={"number": phone, "presence": "composing",
                  "delay": int(seconds * 1000)},
        )
    except httpx.HTTPError:
        pass  # typing gagal bukan alasan membatalkan pengiriman pesan


async def send_text(client: httpx.AsyncClient, phone: str, text: str) -> bool:
    """Kirim satu bubble teks."""
    try:
        resp = await client.post(
            f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}",
            headers=HEADERS,
            json={"number": phone, "text": text},
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        print(f"  [whatsapp] Gagal kirim ke {phone}: {e}")
        return False



async def send_reply(phone: str, reply: str) -> None:
    """Kirim jawaban AI lengkap: bersihkan marker, pecah bubble, kirim manusiawi.

    - [WAIT] dan [HANDOVER] adalah marker internal -> dibuang dari teks
    (deteksi [HANDOVER] dilakukan di main.py SEBELUM fungsi ini dipanggil)
    - [NEXT] memecah jadi bubble terpisah, dikirim berurutan dengan
    typing indicator + jeda proporsional
    """
    clean = reply.replace("[WAIT]", "").replace("[HANDOVER]", "")
    # Pecah bubble di [NEXT] ATAU baris kosong (\n\n) -> tiap paragraf jadi bubble sendiri
    bubbles = [b.strip() for b in re.split(r"\[NEXT\]|\n\s*\n", clean) if b.strip()]

    async with httpx.AsyncClient(timeout=30) as client:
        for bubble in bubbles:
            duration = _typing_duration(bubble)
            await send_typing(client, phone, duration)
            await asyncio.sleep(duration)
            await send_text(client, phone, bubble)



def extract_incoming(payload: dict) -> dict | None:
    """Parse webhook 'messages.upsert' Evolution API -> {phone, text, name}.

    Return None untuk event yang harus DIABAIKAN:
    - pesan dari diri sendiri (fromMe) -> mencegah AI membalas dirinya = loop
    - pesan grup (@g.us) -> agent ini untuk chat personal
    - non-teks (gambar/voice) -> di luar scope workshop
    """
    data = payload.get("data") or {}
    key = data.get("key") or {}
    remote_jid: str = key.get("remoteJid", "")

    if key.get("fromMe"):
        return None
    if "@g.us" in remote_jid:           # grup
        return None
    if not remote_jid.endswith("@s.whatsapp.net"):
        return None

    message = data.get("message") or {}
    text = (message.get("conversation")
            or (message.get("extendedTextMessage") or {}).get("text"))
    if not text:
        return None                      # non-teks

    return {
        "phone": remote_jid.split("@")[0],
        "text": text,
        "name": data.get("pushName"),
    }