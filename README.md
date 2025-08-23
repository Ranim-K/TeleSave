# Telegram Media Downloader

An interactive Telegram media downloader built with [Telethon](https://github.com/LonamiWebs/Telethon) and [Rich](https://github.com/Textualize/rich).

## ✨ Features
- Download **photos, videos, or both** from chats, channels, or groups  
- Save **albums (grouped media)** into their own folders  
- Avoid duplicates with **unique filenames** and per-chat **download logs**  
- **Progress bar** with ETA, skipped/finished summary  
- Config saved in `config.json` (API ID and API Hash)  

## 🚀 Usage
1. Install requirements:
   ```bash
   pip install telethon rich
Run the script:

python telegram_media_downloader.py


2. On first run:

Enter your Telegram API ID and API Hash (get them from my.telegram.org
)

Enter the chat username/ID (e.g., @channelname)

Choose media type, quantity, and order

Confirm to start downloading

📂 Downloaded Files

Files are saved in downloads/<chat_name>/

Albums are stored inside group_<group_id>/ subfolders

Each chat keeps a _downloaded.json log of already downloaded message IDs


---

### 📌 Uploading to GitHub  

1. **Create a repository** on [GitHub](https://github.com/new)  
   - Give it a name (e.g., `telegram-media-downloader`).  
   - Keep it **Public** (or Private if you prefer).  
   - Don’t add any files (we’ll push from local).  

2. **Open a terminal in your project folder** (where your `.py` and `README.md` are).  

3. Run these commands (replace `<your-username>` and `<repo-name>`):  
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Telegram Media Downloader"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
4. Refresh your GitHub repo page → your code + README will be there 🎉
