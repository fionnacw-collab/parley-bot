@echo off
title Deploy to Hugging Face Spaces
echo ========================================================
echo   Auto-Deploy Parley Bot to Hugging Face Spaces (FREE)
echo ========================================================
pip install python-dotenv huggingface_hub
python deploy_hf.py
pause
