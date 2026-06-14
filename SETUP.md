# Setup Environment — Mulai dari Proyek Kosong

Panduan ini untuk membuat proyek **dari nol** (folder masih kosong). Butuh **Python 3.12+**.
Pilih SALAH SATU jalur. Dependency yang kita pasang sama untuk keduanya:

```
fastapi   uvicorn   google-genai   sqlmodel   python-dotenv   httpx
```

> Jalur A (uv) = paling cepat, otomatis mengunci versi. Jalur B (Python biasa) = tanpa tool tambahan.

---

## Jalur A — uv (rekomendasi)

### 1. Install uv (sekali saja)

| | Perintah |
|---|---|
| **Windows** (PowerShell) | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| **Mac / Linux** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

Tutup lalu buka ulang terminal, cek: `uv --version`

### 2. Buat proyek baru di folder kosong

```bash
uv init .                 # bikin pyproject.toml di folder ini
uv python pin 3.12        # kunci versi Python ke 3.12
```

### 3. Tambahkan dependency

```bash
uv add fastapi uvicorn google-genai sqlmodel python-dotenv httpx
```
(Otomatis bikin virtual env `.venv`, install, dan mengunci versi di `uv.lock`. Tidak perlu aktivasi manual.)

### 4. Jalankan (sama persis di Windows & Mac)

```bash
uv run python database.py                       # cek fondasi data
uv run python cli.py                             # ngobrol dengan AI di terminal
uv run uvicorn main:app --reload --port 8000     # jalankan server WhatsApp
```

---

## Jalur B — Python biasa (venv + pip)

### 1. Bikin virtual environment

| | Perintah |
|---|---|
| **Windows** | `python -m venv .venv` |
| **Mac / Linux** | `python3 -m venv .venv` |

### 2. Aktifkan virtual environment  ← **satu-satunya perintah yang beda OS**

| | Perintah |
|---|---|
| **Windows** (PowerShell) | `.venv\Scripts\Activate.ps1` |
| **Windows** (CMD) | `.venv\Scripts\activate.bat` |
| **Mac / Linux** | `source .venv/bin/activate` |

Berhasil kalau prompt diawali `(.venv)`.

> Windows PowerShell menolak dengan error *execution policy*? Jalankan sekali:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 3. Tambahkan dependency

```bash
pip install fastapi uvicorn google-genai sqlmodel python-dotenv httpx
pip freeze > requirements.txt     # (opsional) simpan daftar versi
```

### 4. Jalankan (setelah venv aktif, sama di semua OS)

```bash
python database.py                            # cek fondasi data
python cli.py                                  # ngobrol dengan AI di terminal
uvicorn main:app --reload --port 8000          # jalankan server WhatsApp
```

> Di Mac, untuk bikin venv pakai `python3`. Setelah venv aktif, cukup `python`.

---

## Perbandingan singkat

| Langkah | Jalur A — uv | Jalur B — Python biasa |
|---|---|---|
| Inisialisasi | `uv init .` | `python -m venv .venv` |
| Aktivasi env | tidak perlu | wajib (`activate`, beda per-OS) |
| Tambah deps | `uv add <paket>` | `pip install <paket>` |
| Versi terkunci | ya (`uv.lock`) | tidak (kecuali `pip freeze`) |
| Menjalankan | `uv run <perintah>` | `<perintah>` (env harus aktif) |

**Inti perbedaan:** uv tidak butuh aktivasi dan tiap perintah diawali `uv run`. Python biasa butuh aktivasi venv sekali, lalu perintah dijalankan tanpa prefix.

---

## Langkah berikutnya (kedua jalur)

1. Buat file rahasia `.env` dan kunci dari Git:
   ```
   # .gitignore
   .env
   *.db
   .venv
   __pycache__/
   ```
2. Isi `.env` (minimal `GEMINI_API_KEY`), lalu mulai menulis kode dari `database.py` (lihat Babak 3 di naskah workshop).
3. Untuk menyambung ke WhatsApp nanti: `ngrok http 8000` di terminal terpisah.
