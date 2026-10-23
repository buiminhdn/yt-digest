#!/usr/bin/env python3
"""Lấy TELEGRAM_CHAT_ID: nhắn một tin bất kỳ cho bot trước, rồi chạy
    python digest/get_chat_id.py <BOT_TOKEN>
"""
import sys

import requests

if len(sys.argv) != 2:
    sys.exit("Cách dùng: python digest/get_chat_id.py <BOT_TOKEN>")

r = requests.get(f"https://api.telegram.org/bot{sys.argv[1]}/getUpdates", timeout=30).json()
chats = {u["message"]["chat"]["id"]: u["message"]["chat"].get("first_name") or u["message"]["chat"].get("title")
         for u in r.get("result", []) if "message" in u}
if not chats:
    sys.exit("Chưa thấy tin nhắn nào. Mở Telegram, nhắn 'hi' cho bot rồi chạy lại.")
for cid, name in chats.items():
    print(f"TELEGRAM_CHAT_ID = {cid}   ({name})")
