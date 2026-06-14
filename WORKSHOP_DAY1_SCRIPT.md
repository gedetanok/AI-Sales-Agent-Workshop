# Day 1 — Membangun Engine AI Sales Agent on WhatsApp
### Naskah pengajaran (± 3 jam)

Alur naskah ini tiga babak: **(1)** kita pahami dulu sistemnya secara utuh, **(2)** kita bedah arsitekturnya dan—yang paling penting—*kenapa* dirancang begitu, lalu **(3)** kita bangun dari nol, selangkah demi selangkah, sambil mengetes tiap milestone.

---

# BABAK 1 — Gambaran Umum Sistem

*(±20 menit. Tujuan: sebelum ngoding, semua orang punya peta yang sama di kepala.)*

Yang akan kita bangun hari ini adalah seorang "customer service + sales" yang tidak pernah tidur. Dia hidup di WhatsApp sebuah klinik kecantikan, bisa menjawab pertanyaan treatment, menjelaskan harga, dan yang paling penting: benar-benar mencatat booking ke sistem, bukan cuma ngobrol. Dari sisi customer, dia terasa seperti admin manusia yang ramah. Dari sisi kita, dia adalah sebuah program Python yang menyambungkan WhatsApp ke sebuah "otak" AI.

Cara paling gampang memahaminya adalah dengan mengikuti **perjalanan satu pesan**. Bayangkan seorang customer mengetik "halo" di WhatsApp:

```
Customer (WhatsApp)
   │  "halo"
   ▼
Evolution API         ← server yang "ngerti bahasa WhatsApp"
   │  webhook
   ▼
ngrok                 ← alamat publik sementara menuju laptop kita
   │
   ▼
FastAPI /webhook      ← "kantor" kita (main.py), nerima & menunda sebentar
   │
   ▼
Agent (Gemini)        ← "otak": mutusin harus ngapain
   │   ├─ tools  ──► Database   (baca harga, cek slot, simpan booking)
   │   └─ memory ──► riwayat chat
   ▼
balasan dipecah jadi bubble + efek "mengetik"
   ▼
Evolution API ──► Customer (WhatsApp)
```

Pesannya bergerak dari kanan (customer) masuk ke kiri (sistem kita), diproses, lalu balasannya keluar lagi ke customer. Tidak ada satu pun bagian yang sihir—semuanya potongan kecil yang punya satu tugas.

Supaya gampang diingat, kelompokkan jadi lima peran:

- **Si kurir** — Evolution API, ngrok, dan file `whatsapp.py`. Tugasnya cuma mengantar pesan masuk dan keluar. Tidak berpikir.
- **Si otak** — `agent.py` plus model Gemini. Dia yang memutuskan: ini harus dijawab langsung, atau perlu cek database dulu?
- **Si kepribadian** — `prompts/system.md`. Ini "SOP karyawan": cara bicara, aturan jualan, kapan menyerah ke admin. Diganti tanpa menyentuh kode.
- **Si ingatan** — `memory.py`. Supaya percakapan nyambung dan admin bisa ambil alih.
- **Si sumber kebenaran** — `database.py` dan `tools.py`. Semua harga, jadwal, dan booking ada di sini. Otak tidak boleh mengarang; dia harus bertanya ke sini.

> **Cara membawakan:** tunjukkan dulu hasil akhirnya—chat WhatsApp yang sudah jalan dan bisa booking. Biarkan mereka kagum dan penasaran "kok bisa?". Baru bilang: "Tiga jam ke depan, kita bongkar dan bangun ini bareng-bareng, dari nol."

---

# BABAK 2 — Arsitektur & Alasan di Baliknya

*(±40 menit. Tujuan: paham bukan cuma "apa", tapi "kenapa begini". Ini yang membuat mereka bisa membangun ulang, bukan sekadar menyalin.)*

Babak ini kita belum ngoding. Kita jalan-jalan ke tiap keputusan desain dan membahas alasannya. Setiap kali murid paham "kenapa", kode di Babak 3 jadi terasa wajar, bukan mantra yang dihafal.

### Kenapa dipecah jadi banyak file kecil?

Kita bisa saja menumpuk semuanya di satu file raksasa. Tapi kita pisah: data di `database.py`, aksi di `tools.py`, otak di `agent.py`, ingatan di `memory.py`, jembatan di `whatsapp.py`, kepribadian di `prompts/system.md`. Alasannya satu kata: **bisa diganti.** Karena ini template yang mau dijual ke banyak klien, kita ingin bisa mengganti kepribadian untuk klinik A tanpa menyentuh logika booking, atau pindah dari WhatsApp ke Telegram tanpa mengubah otak. Tiap file punya satu tanggung jawab, jadi perubahan di satu tempat tidak meledakkan tempat lain.

### Kenapa database jadi "sumber kebenaran", dan AI dilarang mengarang?

Ini fondasi yang membedakan *agent* dari *chatbot biasa*. Chatbot biasa menjawab dari ingatan model—dan model AI gemar mengarang harga yang terdengar meyakinkan tapi salah. Untuk bisnis nyata, itu fatal. Maka aturannya tegas: semua harga, jadwal, dan ketersediaan **hanya** boleh datang dari database. AI tidak menyentuh database langsung; dia harus lewat **tools**. Tools inilah satu-satunya pintu, dan pintu itu yang menegakkan aturan. Kita pakai SQLite karena nol setup (cukup satu file `clinic.db`); saat produksi tinggal ganti alamat database ke Postgres, kodenya tidak berubah.

### Kenapa booking-nya "capacity-based" dan dicek secara atomik?

Klinik punya 3 perawat, jadi tiga customer *boleh* di jam yang sama. Slot baru penuh kalau ketiga perawat sibuk di rentang 90 menit yang tumpang-tindih. Ini lebih realistis daripada "satu jam untuk satu orang". Tapi ada jebakan klasik: kalau dua orang menekan "booking" di detik yang sama, keduanya bisa lolos dan jadi *overbooking*. Solusinya, fungsi `book_treatment` mengecek kapasitas **dan** menyimpan dalam satu transaksi yang tak bisa disela. Inilah kenapa booking jadi "satu sumber kebenaran"—keputusan final hanya terjadi di satu titik, sehingga aman dari kondisi balapan.

### Kenapa pakai pola "tool calling"?

Otak (Gemini) tidak mengeksekusi apa-apa sendiri. Saat dia butuh data, dia tidak menebak—dia "mengangkat tangan" dan bilang "tolong panggilkan `search_treatments` dengan kata kunci acne". Program kita yang menjalankan fungsi itu, lalu mengembalikan hasilnya ke Gemini, dan Gemini menyusun jawaban dari data nyata. Ini berputar sampai Gemini puas dan memberi jawaban teks. Pola inilah yang mengubah "model yang ngobrol" menjadi "asisten yang bisa bertindak".

### Kenapa kepribadian dipisah ke file teks, bukan di kode?

`prompts/system.md` adalah "SOP karyawan": nada bicara, aturan tidak boleh ngaku bot, kapan menyerahkan chat ke admin, cara memecah pesan jadi beberapa bubble. Kita taruh terpisah karena ini yang paling sering diubah per klien—dan kita ingin mengubah karakter AI hanya dengan menyunting teks, tanpa takut merusak logika. Satu pelajaran penting yang akan kita bahas: prompt harus *cocok dengan tool yang benar-benar ada*. Kalau prompt menyebut kemampuan yang tidak ada tool-nya, AI jadi bingung dan kaku.

### Kenapa otak butuh "ingatan", dan kenapa terbatas?

Tanpa ingatan, tiap pesan seperti kenalan baru—AI lupa customer barusan bilang apa. Maka kita simpan riwayat. Tapi kita batasi hanya N pesan terakhir (*sliding window*), karena mengirim seluruh riwayat ke AI itu mahal dan lambat. Di ingatan ini juga ada "saklar": kalau AI menyerah dan menyerahkan ke admin, saklarnya dimatikan supaya AI berhenti membalas nomor itu sampai admin selesai. Ingatan ini dibungkus jadi satu lapisan tersendiri supaya kalau besok mau pindah ke Redis, cukup ganti lapisan itu.

### Kenapa perlu Evolution API + ngrok + webhook?

Kita tidak bisa menyambung ke WhatsApp langsung; WhatsApp tidak membuka pintunya untuk sembarang program. Evolution API adalah perantara yang sudah "fasih bahasa WhatsApp"—kita cukup bicara HTTP biasa dengannya. Saat ada pesan masuk, Evolution perlu memberi tahu kita lewat *webhook*, yaitu dia menelepon sebuah alamat URL milik kita. Masalahnya laptop kita tidak punya alamat publik. Di situ ngrok masuk: dia memberi kita URL publik sementara yang meneruskan ke laptop. Saat produksi, ngrok diganti server beneran.

### Kenapa pesan ditunda dulu (buffer), bukan langsung dibalas?

Perhatikan kebiasaan orang di WhatsApp: mereka mengetik beruntun—"halo" ... "kak" ... "mau nanya dong". Kalau tiap pesan langsung diproses, AI akan menjawab tiga kali dan terasa kaku. Maka kita tunggu beberapa detik, gabungkan pesan-pesan yang berdekatan jadi satu, baru proses. Timernya di-reset tiap ada pesan baru. Hasilnya AI merespons seperti manusia yang menunggu lawan bicara selesai mengetik. Ditambah efek "sedang mengetik..." dan balasan yang dipecah jadi beberapa bubble, percakapan terasa alami—bukan robot yang menyemburkan satu paragraf panjang.

> **Cara membawakan:** untuk tiap keputusan, ajukan dulu "masalahnya" baru "solusinya". Contoh: "Kalau dua orang booking barengan, gimana biar nggak dobel?" → biarkan mereka berpikir → baru jelaskan atomic check. Pemahaman yang lahir dari pertanyaan jauh lebih lengket.

---

# BABAK 3 — Membangun Step by Step (Code-Along)

*(±2 jam. Tujuan: bangun dari nol mengikuti urutan yang logis—tiap langkah bisa dites sebelum lanjut.)*

Urutan ini penting: kita **tidak** mulai dari WhatsApp. Kita mulai dari fondasi data, naik perlahan, dan baru menyentuh WhatsApp di akhir. Tujuannya, di tengah jalan kita sudah bisa "ngobrol" dengan AI lewat terminal—tanpa ribet WhatsApp—dan tahu otaknya sudah benar sebelum disambungkan.

> **Cara membawakan code-along:** tulis kode bertahap, jalankan tiap selesai satu file, dan jangan lanjut sebelum yang sekarang hijau. Tiap potongan di bawah adalah bagian *kunci* yang wajib dijelaskan—sisanya (import, detail kecil) boleh disalin sambil lalu.

---

### Langkah 0 — Fondasi proyek & rahasia

Bikin folder, pasang dependency (`fastapi`, `uvicorn`, `google-genai`, `sqlmodel`, `httpx`, `python-dotenv`), lalu buat dua file yang menentukan: `.env` (rahasia asli) dan `.env.example` (contoh kosong untuk dibagikan). Kuncinya, lindungi rahasia dari Git sejak detik pertama:

```gitignore
# .gitignore
.env
*.db
__pycache__/
.venv
media/
```

```bash
# .env  (JANGAN pernah di-commit)
GEMINI_API_KEY=isi_punyamu
GEMINI_MODEL=gemini-3.1-flash-lite
DATABASE_URL=sqlite:///clinic.db
EVOLUTION_API_URL=https://....zeabur.app
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE=glowria
BUFFER_SECONDS=8
```

**Narasi:** "Aturan nomor satu: API key tidak pernah masuk Git. Sekali bocor ke repo publik, dalam hitungan jam bisa diblokir otomatis. Maka `.env` kita kunci di `.gitignore` sekarang, sebelum nulis kode apa pun."

*Milestone:* proyek bisa dijalankan, `.env` aman.

---

### Langkah 1 — Data: `database.py`

Pertama atur koneksi database. Satu baris `DATABASE_URL` inilah yang membuat kita bisa pindah dari SQLite ke Postgres tanpa ubah kode lain:

```python
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///clinic.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

TREATMENT_DURATION_MINUTES = 90   # 1 treatment = 90 menit
MAX_CONCURRENT = 3                # 3 perawat paralel
```

Lalu tiap tabel = satu class. Tunjukkan satu yang sederhana (`Treatment`) dan satu yang jadi pusat transaksi (`Booking`):

```python
class Treatment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    category: str = Field(index=True)
    price: int
    description: str                       # <- "manfaat", dipakai AI buat edukasi
    promo: Optional[str] = None
    requires_doctor: bool = Field(default=False)

class Booking(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)         # GLW-20260613-A3F1
    customer_name: str
    phone: str = Field(index=True)
    treatment_id: int = Field(foreign_key="treatment.id")
    booking_date: date = Field(index=True)
    booking_time: time
    duration_minutes: int = Field(default=TREATMENT_DURATION_MINUTES)
    status: str = Field(default="pending", index=True)  # pending|confirmed|cancelled
```

Terakhir, fungsi untuk membuat tabel dan mengisi data contoh, dibuat *idempotent* (aman dijalankan berkali-kali):

```python
def init_db():
    SQLModel.metadata.create_all(engine)

def seed_db():
    with Session(engine) as session:
        if session.exec(select(Treatment)).first():
            return                          # sudah ada, jangan dobel
        session.add_all(SEED_TREATMENTS + SEED_HOURS + SEED_DOCTORS + SEED_SPECIAL)
        session.commit()
```

**Narasi:** "Perhatikan dua angka di atas—90 menit dan 3 perawat. Kelihatan sepele, tapi keduanya jadi dasar seluruh logika booking nanti. Dan `description` di Treatment bukan hiasan: itu 'manfaat' yang nanti dipakai AI untuk mengedukasi customer, bukan cuma menyebut harga."

*Dites dengan:* `uv run python database.py` → seluruh treatment & jadwal tercetak. Sistem sekarang punya "kebenaran" untuk dirujuk.

---

### Langkah 2 — Aksi: `tools.py` (jantung sistem)

Mulai dari potongan paling penting di seluruh hari ini: cara menghitung slot penuh. Bukan "satu jam satu orang", tapi berapa booking yang *tumpang-tindih* dengan rentang 90 menit:

```python
def _count_overlap(session, d, start, duration=TREATMENT_DURATION_MINUTES):
    s1, e1 = _minutes(start), _minutes(start) + duration
    bookings = session.exec(select(Booking).where(
        Booking.booking_date == d,
        Booking.status != "cancelled",
    )).all()
    count = 0
    for b in bookings:
        s2 = _minutes(b.booking_time); e2 = s2 + b.duration_minutes
        if s1 < e2 and s2 < e1:        # rumus overlap dua rentang waktu
            count += 1
    return count
```

Lalu `book_treatment`—satu-satunya pintu untuk menyimpan booking, dengan validasi berlapis lalu insert, semuanya dalam satu sesi:

```python
def book_treatment(customer_name, phone, treatment_name, booking_date, booking_time):
    d = _parse_date(booking_date); t = _parse_time(booking_time)
    with get_session() as session:
        rules = _get_day_rules(session, d)

        if rules["is_closed"]:                       # 1. klinik tutup?
            return {"success": False, "error": "CLINIC_CLOSED", ...}

        start_m = _minutes(t)
        now = datetime.now()                         # 2. waktu sudah lewat?
        if d < now.date() or (d == now.date() and start_m <= _minutes(now.time())):
            return {"success": False, "error": "PAST_TIME",
                    "next_available_slot": _next_available_slot(session, d, now.time(), rules)}

        last_valid = _minutes(rules["close"]) - TREATMENT_DURATION_MINUTES
        if start_m < _minutes(rules["open"]) or start_m > last_valid:   # 3. di luar jam?
            return {"success": False, "error": "OUTSIDE_HOURS", ...}

        if _count_overlap(session, d, t) >= MAX_CONCURRENT:            # 4. slot penuh?
            return {"success": False, "error": "SLOT_CONFLICT",
                    "next_available_slot": _next_available_slot(session, d, t, rules)}

        booking = Booking(code=_generate_code(), customer_name=customer_name,
                          phone=phone, treatment_id=treatment.id,
                          booking_date=d, booking_time=t)
        session.add(booking); session.commit()       # cek + simpan = satu transaksi
        return {"success": True, "booking_code": booking.code, ...}
```

Setiap tool punya "kartu nama" yang dibaca Gemini—inilah yang menentukan kapan AI memanggilnya:

```python
TOOL_DECLARATIONS = [{
    "name": "search_treatments",
    "description": ("Cari treatment berdasarkan kata kunci. WAJIB dipanggil "
                    "sebelum menyebut nama/harga treatment apapun. Jangan mengarang."),
    "parameters": {"type": "object",
        "properties": {"query": {"type": "string"}}, "required": ["query"]},
}, ...]

TOOL_FUNCTIONS = {"search_treatments": search_treatments,
                  "book_treatment": book_treatment, ...}   # nama -> fungsi asli
```

**Narasi:** "Belum ada AI satu baris pun di sini. Ini Python murni. Coba pikirkan: kenapa cek slot dan simpan harus dalam satu transaksi?" → biarkan mereka jawab → "Supaya dua orang yang booking di detik yang sama tidak sama-sama lolos. Inilah arti 'satu sumber kebenaran'."

*Dites dengan:* `uv run python tools.py` → 9 skenario (sukses, slot penuh menawarkan jam berikut, di luar jam, klinik tutup, cancel, dst).

---

### Langkah 3 — Otak: `agent.py` (milestone besar #1)

Inti seluruh agent adalah satu perputaran. Kirim pesan ke Gemini; kalau dia minta tool, jalankan dan kembalikan hasilnya; ulang sampai dia memberi jawaban teks:

```python
def run_agent(history, user_message, phone, images=None):
    now = datetime.now()                  # tanggal/jam disuntik PER PESAN -> selalu segar
    date_ctx = f"Hari ini {HARI[now.weekday()]} {now:%Y-%m-%d}, pukul {now:%H:%M}"

    parts = [types.Part(text=f"[Konteks: {date_ctx}. Nomor: {phone}]\n{user_message}")]
    for img_bytes, mime in (images or []):                 # dukungan baca gambar
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))

    contents = list(history)
    contents.append(types.Content(role="user", parts=parts))

    for _ in range(MAX_TOOL_ITERATIONS):                   # loop, bukan sekali jalan
        response = client.models.generate_content(
            model=MODEL, contents=contents, config=GENERATE_CONFIG)
        contents.append(response.candidates[0].content)

        calls = response.function_calls or []
        if not calls:
            return response.text, contents                 # tidak minta tool -> jawaban final

        for fc in calls:                                   # eksekusi tiap tool yang diminta
            func = TOOL_FUNCTIONS.get(fc.name)
            result = func(**dict(fc.args))
            contents.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=fc.name, response={"result": result})]))
```

Konfigurasi yang menyatukan kepribadian (system prompt) + daftar tool:

```python
GENERATE_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,                            # dari prompts/system.md
    tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
)
```

**Narasi:** "Lihat dua hal. Pertama, ini *loop*—Gemini bisa minta tool, kita kasih hasil, dia minta tool lagi, baru menjawab. Itu yang bikin dia 'bertindak', bukan cuma ngobrol. Kedua, tanggal dan jam kita selipkan di tiap pesan, bukan di kepribadian, supaya kepribadiannya tetap sama sepanjang hari (hemat & cepat) tapi waktunya selalu update."

*Dites dengan:* `uv run python cli.py` → **milestone besar pertama.** Ngobrol + booking langsung di terminal, tanpa WhatsApp. Saat tanya treatment, muncul `[tool] search_treatments(...)`—otak dan tangan sudah menyatu.

---

### Langkah 4 — Ingatan: `memory.py`

Bungkus akses riwayat jadi satu lapisan, dengan tiga kemampuan: ambil N pesan terakhir, simpan pesan, dan saklar takeover.

```python
class Memory:
    def get_history(self, phone):                     # sliding window: N terakhir saja
        with get_session() as s:
            rows = s.exec(select(ConversationMessage)
                .where(ConversationMessage.phone == phone)
                .order_by(ConversationMessage.created_at.desc())
                .limit(MEMORY_WINDOW)).all()
        rows = list(reversed(rows))
        return [types.Content(role=m.role, parts=[types.Part(text=m.text)]) for m in rows]

    def add(self, phone, role, text):
        with get_session() as s:
            s.add(ConversationMessage(phone=phone, role=role, text=text)); s.commit()

    def is_ai_enabled(self, phone):                   # saklar takeover
        with get_session() as s:
            c = s.get(Contact, phone)
            return c.ai_enabled if c else True

memory = Memory()
```

**Narasi:** "Kenapa cuma N terakhir? Karena mengirim seluruh riwayat ke AI itu mahal dan lambat. Dan kenapa dibungkus jadi class? Supaya kalau besok mau pindah ke Redis, cukup ganti isi class ini—agent dan webhook tidak tahu apa-apa dan tidak perlu diubah."

*Milestone:* `uv run python memory.py` → riwayat tersimpan & terambil; saklar takeover nyala/mati.

---

### Langkah 5 — Jembatan WhatsApp: `whatsapp.py`

Dua arah. Membaca pesan masuk (saring yang harus diabaikan, deteksi teks vs gambar):

```python
def extract_incoming(payload):
    data = payload.get("data") or {}
    key = data.get("key") or {}
    remote = key.get("remoteJid", "")
    if key.get("fromMe"):           return None   # pesan kita sendiri -> cegah loop!
    if "@g.us" in remote:           return None   # grup -> abaikan
    msg = data.get("message") or {}
    if msg.get("imageMessage"):                    # GAMBAR
        return {"phone": remote.split("@")[0], "media_type": "image",
                "text": msg["imageMessage"].get("caption") or "", "message": data}
    text = msg.get("conversation") or (msg.get("extendedTextMessage") or {}).get("text")
    return {"phone": remote.split("@")[0], "text": text, "media_type": None} if text else None
```

Mengirim balasan secara manusiawi (pecah bubble + efek mengetik):

```python
async def send_reply(phone, reply):
    bubbles = [b.strip() for b in re.split(r"\[NEXT\]|\n\s*\n", reply) if b.strip()]
    async with httpx.AsyncClient() as client:
        for bubble in bubbles:
            dur = _typing_duration(bubble)
            await send_typing(client, phone, dur)   # "sedang mengetik..."
            await asyncio.sleep(dur)                 # jeda proporsional
            await send_text(client, phone, bubble)
```

**Narasi:** "Baris `fromMe` itu krusial—tanpa itu, AI akan membaca balasannya sendiri sebagai pesan masuk dan membalas dirinya terus-menerus. Loop tak berujung. Dan `send_reply` inilah yang bikin terasa manusiawi: bukan satu paragraf nyembur, tapi beberapa bubble dengan jeda dan efek mengetik."

*Milestone:* paham bentuk data masuk/keluar WhatsApp.

---

### Langkah 6 — Orkestrator: `main.py` (milestone besar #2)

Webhook harus membalas cepat, jadi kerja berat dilempar ke background dengan timer yang di-reset tiap pesan baru (inilah debounce):

```python
@app.post("/webhook")
async def webhook(request: Request):
    incoming = extract_incoming(await request.json())
    if incoming is None: return {"status": "ignored"}
    phone = incoming["phone"]
    buffers[phone].append(incoming)        # kumpulkan dulu
    schedule_processing(phone)             # reset timer 8 detik
    return {"status": "buffered"}          # balas cepat, proses nanti

def schedule_processing(phone):
    old = buffer_tasks.get(phone)
    if old and not old.done(): old.cancel()    # batalkan timer lama -> reset
    buffer_tasks[phone] = asyncio.create_task(process_buffered_messages(phone))
```

Setelah timer habis: gabung pesan, cek saklar takeover, panggil otak, deteksi handover, balas:

```python
async def process_buffered_messages(phone):
    await asyncio.sleep(BUFFER_SECONDS)             # tunggu; di-cancel kalau ada pesan baru
    pending = buffers.pop(phone, [])
    combined = "\n".join(i["text"] for i in pending if i.get("text"))

    if not memory.is_ai_enabled(phone):             # admin lagi pegang? AI diam
        memory.add(phone, "user", combined); return

    history = memory.get_history(phone)
    reply, _ = await asyncio.to_thread(run_agent, history, combined, phone)
    memory.add(phone, "user", combined); memory.add(phone, "model", reply)

    if "[HANDOVER]" in reply:                        # AI menyerah -> matikan utk nomor ini
        memory.set_ai_enabled(phone, False)
    await send_reply(phone, reply)
```

**Narasi:** "Dua ide besar di sini. Satu, webhook membalas dalam sepersekian detik lalu memproses di belakang—kalau lambat, Evolution menganggap gagal dan mengirim ulang. Dua, timer 8 detik yang di-reset tiap pesan: itulah yang menggabungkan 'halo'...'kak'...'mau nanya' jadi satu, biar AI menjawab sekali seperti manusia."

*Dites dengan:* `uv run uvicorn main:app --reload --port 8000` → `ngrok http 8000` → daftarkan URL `…/webhook` di Evolution → chat dari HP. Amati log `[masuk]` → `[buffer]` → `[balas]`. **AI membalas di WhatsApp asli.**

---

### Langkah 7 — Pemolesan production-ready

Jalan dasar sudah ada. Sekarang sentuhan yang membedakan demo dari produk—tunjukkan bahwa masing-masing cuma perubahan kecil di satu tempat:

- **Guard waktu lewat** (sudah kita selipkan di `book_treatment` tadi): coba booking jam yang sudah lewat → AI menolak sopan, bukan menerima jam mati.
- **Edukasi, bukan daftar harga:** satu aturan di `system.md` membuat AI menyebut manfaat tiap treatment (dari `description`), memimpin dengan 1 rekomendasi paling cocok.
- **Baca gambar:** `Part.from_bytes` di `agent.py` + ambil base64 dari Evolution → customer kirim foto kulit, AI menganalisis.
- **Persona terpisah:** ubah satu kalimat tone di `system.md`, restart, gaya balasan berubah—tanpa menyentuh kode. Inilah kunci "jual ulang" ke klien berbeda.

**Narasi penutup babak:** "Perhatikan, semua pemolesan tadi tidak mengacak-acak sistem. Guard di satu fungsi, tone di satu file teks, baca gambar di satu baris. Itulah buah dari memisahkan tanggung jawab di Babak 2—dan itulah yang bikin ini layak disebut *production ready & resellable*."

---

## Penutup & Jembatan ke Day 2

Hari ini kita membangun **otak dan tangannya**: AI yang bisa berpikir, mengakses data nyata, dan melayani customer di WhatsApp. Besok kita bangun **matanya untuk pemilik klinik**—sebuah dashboard untuk memantau semua percakapan, termasuk foto yang dikirim customer, dan mengambil alih chat saat perlu.

---

## Lampiran — Urutan perintah demo

| Milestone | Perintah |
|---|---|
| Cek fondasi data | `uv run python database.py` |
| Cek tools (tanpa AI) | `uv run python tools.py` |
| Ngobrol dengan AI di terminal | `uv run python cli.py` |
| Cek ingatan | `uv run python memory.py` |
| Jalankan server WhatsApp | `uv run uvicorn main:app --reload --port 8000` |
| Buka tunnel publik | `ngrok http 8000` |
