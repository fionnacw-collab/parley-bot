---
title: Parley Football Bot
emoji: ⚽
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8080
pinned: false
---

# Parley - Deep Football & Parlay Analysis Telegram Bot

Bot Telegram analisis sepak bola & parlay mendalam dengan dukungan AI (GPT-4o Vision), Bivariate Poisson xG modeling, bookmaker odds consensus, dan perhitungan Expected Value (+EV).

## Deployment di Hugging Face Spaces (Docker)

1. Buat Space baru di Hugging Face dengan SDK **Docker** -> **Blank**.
2. Di **Settings** > **Variables and secrets**, tambahkan:
   - `TELEGRAM_BOT_TOKEN`: Token bot Telegram dari @BotFather (Secrets)
   - `OPENAI_API_KEY`: API Key OpenAI (Secrets)
   - `RAPIDAPI_KEY`: API Key API-Football (Opsional)
   - `ODDS_API_KEY`: API Key The Odds API (Opsional)
3. Bot otomatis aktif 24/7 dan melayani request Telegram & HTTP Health Check.
