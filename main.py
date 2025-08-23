# telegram_media_downloader.py
import os
import re
import json
import asyncio
from pathlib import Path
from typing import Dict, Set

from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, DocumentAttributeVideo
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import UserAlreadyParticipantError


from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
    BarColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
    TaskProgressColumn,
    TextColumn,
)

# ===================== CONFIG =====================
CONFIG_FILE = "config.json"
SESSION_NAME = "session"
BASE_DOWNLOADS = Path("downloads")

console = Console()


# ===================== UTILITIES =====================
def load_config() -> Dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(api_id: int, api_hash: str):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"api_id": api_id, "api_hash": api_hash}, f, indent=2)


def sanitize_for_fs(name: str) -> str:
    """Make a clean folder name for the filesystem."""
    if not name:
        return "chat"
    name = re.sub(r"[\\/:*?\"<>|\n\r\t]", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80]  # keep it tidy


def is_photo_message(msg) -> bool:
    return bool(msg and (msg.photo or isinstance(msg.media, MessageMediaPhoto)))


def is_video_message(msg) -> bool:
    if not msg:
        return False
    if getattr(msg, "video", None):
        return True
    doc = getattr(msg, "document", None)
    if not doc:
        return False
    for attr in getattr(doc, "attributes", []) or []:
        if isinstance(attr, DocumentAttributeVideo):
            return True
    return False


def choose_chat_folder(chat) -> Path:
    """One folder per chat/channel."""
    if getattr(chat, "username", None):
        label = f"@{chat.username}"
    elif getattr(chat, "title", None):
        label = chat.title
    else:
        label = f"id_{chat.id}"
    folder = BASE_DOWNLOADS / sanitize_for_fs(label)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def per_chat_log_path(chat_folder: Path) -> Path:
    return chat_folder / "_downloaded.json"


def load_downloaded_set(chat_folder: Path) -> Set[int]:
    log_path = per_chat_log_path(chat_folder)
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                ids = data.get("downloaded_ids", [])
                return set(int(x) for x in ids)
        except Exception:
            return set()
    return set()


def save_downloaded_set(chat_folder: Path, msg_ids: Set[int], chat_meta: Dict):
    log_path = per_chat_log_path(chat_folder)
    payload = {
        "chat_id": chat_meta.get("id"),
        "chat_name": chat_meta.get("name"),
        "downloaded_ids": sorted(list(msg_ids)),
    }
    temp = log_path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(temp, log_path)


def build_unique_filename(msg, default_ext: str = ".bin") -> str:
    """Stable unique name for each file."""
    if msg.file and msg.file.name:
        base = msg.file.name
    else:
        ext = getattr(getattr(msg, "file", None), "ext", None) or default_ext
        base = f"file{ext}"
    return f"msg_{msg.id}_{base}"


# ===================== CORE DOWNLOAD =====================
async def collect_media_messages(client, chat, media_type: str, limit: int, order: str):
    collected = []
    async for msg in client.iter_messages(chat, limit=limit):
        if not msg or not msg.media:
            continue

        if media_type == "photos":
            if is_photo_message(msg):
                collected.append(msg)
        elif media_type == "videos":
            if is_video_message(msg):
                collected.append(msg)
        else:  # both
            if is_photo_message(msg) or is_video_message(msg):
                collected.append(msg)

    if order == "oldest":
        collected.reverse()
    return collected


async def download_messages(client, chat, messages, chat_folder: Path):
    downloaded_ids = load_downloaded_set(chat_folder)
    meta = {
        "id": getattr(chat, "id", None),
        "name": getattr(chat, "title", None) or getattr(chat, "username", None) or str(getattr(chat, "id", "")),
    }

    progress = Progress(
        TextColumn("[bold]Downloading[/bold]"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        expand=True,
        refresh_per_second=2,
        transient=False,
        console=console,
    )

    skipped = 0
    completed = 0

    with progress:
        task = progress.add_task("download", total=len(messages))
        for msg in messages:
            try:
                if msg.id in downloaded_ids:
                    skipped += 1
                    progress.advance(task)
                    continue

                # If part of an album -> put inside group_{id}
                if msg.grouped_id:
                    target_dir = chat_folder / f"group_{msg.grouped_id}"
                    target_dir.mkdir(parents=True, exist_ok=True)
                else:
                    target_dir = chat_folder

                unique_name = build_unique_filename(msg, default_ext=".bin")
                out_path = target_dir / unique_name

                if out_path.exists():
                    downloaded_ids.add(msg.id)
                    skipped += 1
                    progress.advance(task)
                    continue

                await msg.download_media(file=str(out_path))
                downloaded_ids.add(msg.id)
                completed += 1
                progress.advance(task)

            except FloodWaitError as e:
                console.print(f"[yellow]Rate limited. Waiting {e.seconds}s…[/yellow]")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                console.print(f"[red]Error on message {msg.id}: {e}[/red]")
                progress.advance(task)

    save_downloaded_set(chat_folder, downloaded_ids, meta)
    return completed, skipped


# ===================== UI FLOW =====================
async def main():
    console.print(Panel.fit("[bold cyan]Telegram Media Downloader[/bold cyan]\nClean • Album-aware • Safe"))

    cfg = load_config()
    if not cfg:
        console.print("[bold]First time setup[/bold]")
        api_id = int(Prompt.ask("Enter your Telegram API ID"))
        api_hash = Prompt.ask("Enter your Telegram API Hash")
        save_config(api_id, api_hash)
        cfg = {"api_id": api_id, "api_hash": api_hash}
    else:
        console.print(f"Using saved credentials from [i]{CONFIG_FILE}[/i].")

    if Confirm.ask("Do you want to update API credentials?", default=False):
        api_id = int(Prompt.ask("Enter your Telegram API ID"))
        api_hash = Prompt.ask("Enter your Telegram API Hash")
        save_config(api_id, api_hash)
        cfg = {"api_id": api_id, "api_hash": api_hash}

    client = TelegramClient(SESSION_NAME, cfg["api_id"], cfg["api_hash"])
    await client.start()

    chat_query = Prompt.ask("Enter chat username or ID (e.g., @channelname or -1001234567890)")

    if "t.me/+" in chat_query:
        invite_hash = chat_query.split("+", 1)[1]
        try:
            updates = await client(ImportChatInviteRequest(invite_hash))
            chat = updates.chats[0] if updates.chats else None
        except UserAlreadyParticipantError:
            chat = await client.get_entity(chat_query)

    elif "t.me/joinchat/" in chat_query:
        invite_hash = chat_query.split("joinchat/", 1)[1]
        try:
            updates = await client(ImportChatInviteRequest(invite_hash))
            chat = updates.chats[0] if updates.chats else None
        except UserAlreadyParticipantError:
            chat = await client.get_entity(chat_query)

    else:
        chat = await client.get_entity(chat_query)

    if not chat:
        console.print("[red]Could not resolve chat.[/red]")
        await client.disconnect()
        return



    table = Table(title="Download Options", show_header=True, header_style="bold magenta")
    table.add_column("Option")
    table.add_column("Choices / Example")
    table.add_row("Media type", "photos / videos / both")
    table.add_row("Quantity", "how many recent messages to scan (e.g., 1000)")
    table.add_row("Order", "newest / oldest")
    console.print(table)

    media_type = Prompt.ask("Media type?", choices=["photos", "videos", "both"], default="both")
    quantity = int(Prompt.ask("How many recent messages to check?", default="500"))
    order = Prompt.ask("Download order?", choices=["newest", "oldest"], default="oldest")

    chat_folder = choose_chat_folder(chat)
    console.print(f"[green]Destination:[/green] {chat_folder.resolve()}")

    messages = await collect_media_messages(client, chat, media_type, quantity, order)
    console.print(f"[cyan]Found {len(messages)} matching media messages.[/cyan]")

    if not messages:
        console.print("[yellow]Nothing to download with current filters.[/yellow]")
        await client.disconnect()
        return

    if not Confirm.ask("Start downloading now?", default=True):
        await client.disconnect()
        return

    completed, skipped = await download_messages(client, chat, messages, chat_folder)
    console.print(
        Panel.fit(
            f"[bold green]Done![/bold green]\nDownloaded: {completed}\nSkipped (already had): {skipped}",
            title="Summary",
        )
    )

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
