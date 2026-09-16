"""
deploy_hf.py — Otomatisasi deploy bot ke Hugging Face Spaces (Docker).
100% Gratis & Tanpa Kartu Kredit.
"""

from __future__ import annotations

import os
import sys
from dotenv import load_dotenv

load_dotenv()


def main():
    print("=" * 60)
    print("🚀 AUTOMATIC DEPLOY KE HUGGING FACE SPACES (100% GRATIS)")
    print("=" * 60)

    try:
        from huggingface_hub import HfApi, create_repo
    except ImportError:
        print("Menginstall library huggingface_hub...")
        os.system(f"{sys.executable} -m pip install huggingface_hub")
        from huggingface_hub import HfApi, create_repo

    # 1. Dapatkan Token HF
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("\n🔑 Masukkan Hugging Face Access Token kamu:")
        print("   (Dapatkan gratis di https://huggingface.co/settings/tokens)")
        print("   Pastikan pilih tipe token: WRITE\n")
        hf_token = input("HF Access Token (hf_...): ").strip()

    if not hf_token:
        print("❌ Token tidak boleh kosong. Proses dibatalkan.")
        return

    api = HfApi(token=hf_token)

    try:
        user_info = api.whoami()
        username = user_info["name"]
        print(f"\n✅ Berhasil login sebagai: {username}")
    except Exception as e:
        print(f"\n❌ Gagal memvalidasi token Hugging Face: {e}")
        return

    space_name = "parley-bot"
    repo_id = f"{username}/{space_name}"

    print(f"\n📦 Menyiapkan Space: https://huggingface.co/spaces/{repo_id} ...")

    # 2. Buat Space jika belum ada
    try:
        create_repo(
            repo_id=repo_id,
            repo_type="space",
            space_sdk="docker",
            private=True,
            token=hf_token,
            exist_ok=True,
        )
        print("✅ Space Docker berhasil dibuat/ditemukan.")
    except Exception as e:
        print(f"⚠️ Catatan pembuatan repo: {e}")

    # 3. Sinkronisasi Secrets dari .env
    print("\n🔒 Mengunggah Secrets (API Keys) ke Hugging Face...")
    secrets = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "RAPIDAPI_KEY": os.getenv("RAPIDAPI_KEY", ""),
        "ODDS_API_KEY": os.getenv("ODDS_API_KEY", ""),
    }

    for key, val in secrets.items():
        if val and not val.startswith("your_") and not val.startswith("API_KEY"):
            try:
                api.add_space_secret(repo_id=repo_id, key=key, value=val)
                print(f"  ✓ Secret '{key}' berhasil disetel.")
            except Exception as e:
                print(f"  ⚠️ Gagal menyetel secret '{key}': {e}")

    # 4. Upload Files ke Space
    print("\n📤 Mengunggah source code ke Hugging Face Space...")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        api.upload_folder(
            repo_id=repo_id,
            repo_type="space",
            folder_path=current_dir,
            ignore_patterns=[
                ".git",
                ".git/**",
                "__pycache__",
                "__pycache__/**",
                "*.pyc",
                ".env",
                "*.bat",
                "run.bat",
                "deploy_hf.bat",
            ],
            commit_message="Deploy Parley Bot via deploy_hf.py",
        )
        print("✅ Semua file berhasil diunggah!")
    except Exception as e:
        print(f"❌ Gagal mengunggah file: {e}")
        return

    print("\n" + "=" * 60)
    print("🎉 DEPLOY BERHASIL DIJALANKAN!")
    print(f"🔗 Buka status Space kamu di:")
    print(f"   https://huggingface.co/spaces/{repo_id}")
    print("=" * 60)
    print("Hugging Face sedang mem-build Docker container.")
    print("Dalam 1-2 menit status akan menjadi 'Running' dan bot langsung aktif 24/7.")
    print("=" * 60)


if __name__ == "__main__":
    main()
