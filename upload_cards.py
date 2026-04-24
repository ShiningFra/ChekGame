#!/usr/bin/env python3
"""
upload_cards.py — Upload une seule fois les 54 images vers Telegram
et sauvegarde les file_id dans file_ids.json.

Usage:
    BOT_TOKEN="..." CARDS_CHANNEL_ID="@tonchannel" python upload_cards.py /chemin/vers/images/

Le dossier doit contenir 1.jpg, 2.jpg, ... 54.jpg
"""

import sys
import os
import json
import asyncio
from pathlib import Path
from telegram import Bot

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CARDS_CHANNEL_ID"]   # ex: "@checkgame_cards" ou "-100123456789"
OUTPUT_FILE = "file_ids.json"


async def upload_all(images_dir: Path):
    bot = Bot(token=BOT_TOKEN)
    file_ids = {}

    # Charge les file_ids déjà uploadés si le fichier existe
    if Path(OUTPUT_FILE).exists():
        with open(OUTPUT_FILE) as f:
            file_ids = json.load(f)
        print(f"✅ {len(file_ids)} file_ids déjà en cache.")

    for i in range(1, 55):
        if str(i) in file_ids:
            print(f"  {i:>2}/54 déjà uploadé, skip.")
            continue
        img_path = images_dir / f"{i}.jpg"
        if not img_path.exists():
            print(f"  ⚠️  {img_path} introuvable, skip.")
            continue
        print(f"  Uploading {i}/54 …", end=" ", flush=True)
        with open(img_path, "rb") as f:
            msg = await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=f,
                caption=f"card_{i}",
            )
        fid = msg.photo[-1].file_id
        file_ids[str(i)] = fid
        print(f"OK → {fid[:20]}…")

        # Sauvegarde après chaque upload (sécurité)
        with open(OUTPUT_FILE, "w") as out:
            json.dump(file_ids, out, indent=2)

    print(f"\n✅ Terminé ! {len(file_ids)} file_ids sauvegardés dans {OUTPUT_FILE}")
    print(f"   Copie {OUTPUT_FILE} dans ton dossier bot et définis FILE_IDS_PATH=file_ids.json")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload_cards.py /chemin/vers/images/")
        sys.exit(1)
    images_dir = Path(sys.argv[1])
    asyncio.run(upload_all(images_dir))
