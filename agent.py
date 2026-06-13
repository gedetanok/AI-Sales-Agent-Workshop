import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS

load_dotenv()

# config

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "minimal")  # minimal = cepat & murah
MAX_TOOL_ITERATIONS = 5

AI_NAME = os.getenv("AI_NAME", "Gita")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Glowria Aesthetic Clinic")

FALLBACK_MESSAGE = ("Mohon maaf kak, whatsapp kami sedang ada sedikit kendala🙏[NEXT]"
                    "Admin kami akan segera membantu ya kak 😊[HANDOVER]")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Lazy init: client baru dibuat saat pertama dibutuhkan.

    Dengan ini, import agent.py tidak butuh API key (enak untuk testing),
    dan error 'API key belum diisi' muncul dengan pesan yang jelas.
    """
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY belum diisi. Salin .env.example ke .env "
                            "dan isi API key dari https://aistudio.google.com")
        _client = genai.Client(api_key=api_key)
    return _client

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
        "Agustus", "September", "Oktober", "November", "Desember"]



def render_system_prompt() -> str:
    """Baca prompts/system.md dan isi template variables.

    PENTING untuk caching: hasil render harus sama untuk semua request di
    hari yang sama. Konteks per-customer (nomor HP, history) TIDAK masuk
    sini, melainkan dikirim lewat contents.
    """
    raw = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")

    replacements = {
        "{{aiName}}": AI_NAME,
        "{{companyName}}": COMPANY_NAME,
        # Tanggal/jam TIDAK di-hardcode di sini supaya system prompt tetap statis
        # (cache-friendly). Waktu real-time di-inject per-request via contents di run_agent().
        "{{currentDateContext}}": (
            "Tanggal dan jam SAAT INI selalu diberikan di awal setiap pesan customer "
            "(dalam tanda [Konteks: ...]). Jadikan itu satu-satunya acuan waktu untuk "
            "menghitung 'hari ini', 'besok', 'lusa', dll. JANGAN PERNAH menawarkan atau "
            "menyetujui booking untuk jam yang sudah lewat."
        ),
        # Versi workshop: konteks dinamis ini disederhanakan.
        # Di production, bagian ini diisi data real-time per request.
        "{{bookingContext}}": ("<booking_context>Gunakan tool check_available_schedule dan "
                            "book_treatment untuk status slot real-time. Jangan pernah "
                            "berasumsi soal ketersediaan tanpa hasil tool.</booking_context>"),
        "{{leadContext}}": "Lihat info customer di awal percakapan.",
        "{{conversationSummary}}": "Lihat history percakapan di contents.",
        "{{knowledgeBase}}": ("Gunakan tool search_treatments untuk data treatment dan harga. "
                            "Info klinik statis ada di <clinic_info>."),
        "{{additionalContext}}": "",
    }
    for key, value in replacements.items():
        raw = raw.replace(key, value)
    return raw

SYSTEM_PROMPT = render_system_prompt()

GENERATE_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
    thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
    temperature=0.7,
)


# Agent Core Loop

def run_agent(history: list, user_message: str, phone: str) -> tuple[str, list]:
    """Jalankan satu giliran percakapan.

    Args:
        history: list of types.Content dari giliran-giliran sebelumnya
        user_message: pesan user terbaru (sudah digabung buffer kalau dari WA)
        phone: nomor WhatsApp customer (di-inject supaya tool bisa pakai)

    Returns:
        (jawaban_text, history_baru) -- history_baru sudah termasuk giliran ini,
        siap disimpan oleh memory.py.
    """
    # Nomor HP di-inject sebagai konteks pesan, BUKAN ke system prompt,
    # supaya system prompt tetap statis (cache-friendly).
    now = datetime.now()
    date_ctx = (f"Hari ini {HARI[now.weekday()]}, {now.day} {BULAN[now.month - 1]} {now.year} "
                f"({now:%Y-%m-%d}), pukul {now:%H:%M}")

    contents = list(history)
    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=f"[Konteks: {date_ctx}. Nomor WhatsApp customer: {phone}]\n{user_message}")],
    ))

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = get_client().models.generate_content(
                model=MODEL,
                contents=contents,
                config=GENERATE_CONFIG,
            )

            candidate = response.candidates[0]
            contents.append(candidate.content)  # simpan giliran model (text/function call)

            function_calls = response.function_calls or []
            if not function_calls:
                # Tidak ada tool call -> ini jawaban final
                return (response.text or FALLBACK_MESSAGE), contents

            # Eksekusi SEMUA function call di giliran ini, balikan hasilnya
            result_parts = []
            for fc in function_calls:
                print(f"  [tool] {fc.name}({dict(fc.args)})")  # log untuk demo workshop
                func = TOOL_FUNCTIONS.get(fc.name)
                if func is None:
                    result = {"error": f"Tool '{fc.name}' tidak dikenal."}
                else:
                    try:
                        result = func(**dict(fc.args))
                    except Exception as e:  # tool gagal != agent mati
                        result = {"error": f"Tool gagal: {e}"}
                result_parts.append(types.Part.from_function_response(
                    name=fc.name, response={"result": result},
                ))
            contents.append(types.Content(role="user", parts=result_parts))

        # Loop habis tanpa jawaban text -> jangan biarkan customer digantung
        return FALLBACK_MESSAGE, contents

    except Exception as e:
        print(f"  [error] Gemini API: {e}")
        return FALLBACK_MESSAGE, contents