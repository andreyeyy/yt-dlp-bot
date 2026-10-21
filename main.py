import io
import subprocess
import sys
import asyncio
import os
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def update_yt_dlp(yt_dlp_path) -> None:
    proc = await asyncio.create_subprocess_exec(
        yt_dlp_path,
        "-U",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        message = (stderr or stdout).decode(errors="replace").strip()
        raise RuntimeError(f"yt-dlp update failed: {message}")

    print(stdout.decode(errors="replace").strip())


async def download_video(yt_dlp_path, url, max_bytes = 20 * 1024 * 1024) -> bytes:
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")

    proc = await asyncio.create_subprocess_exec(
        yt_dlp_path,
        "--no-cache-dir",
        "-o", "-",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert proc.stdout is not None
    assert proc.stderr is not None
    data = bytearray()

    try:
        while True:
            remaining = max_bytes + 1 - len(data)
            chunk = await proc.stdout.read(min(64 * 1024, remaining))

            if not chunk:
                break

            data.extend(chunk)
            if len(data) > max_bytes:
                proc.kill()
                await proc.wait()
                raise ValueError(f"Download exceeds {max_bytes} bytes")

        returncode = await proc.wait()
        
        if returncode != 0:
            error_output = await proc.stderr.read()
            error_message = error_output.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"yt-dlp failed for url: {url} (Exit code {returncode}):\n{error_message}")

        return bytes(data)

    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()

async def get(update, context):
    url = ""

    message = update.effective_message
    replied = message.reply_to_message
    await context.bot.set_message_reaction(
        chat_id=message.chat_id,
        message_id=message.message_id,
        reaction="👍",
    )

    print(message.to_dict())

    if not replied is None: # if the command is a reply
        text = replied.text
        if not text is None:
            url = text

    else: # not a reply
        url = " ".join(context.args)

    yt_dlp_path = context.application.bot_data["yt_dlp_path"]
    await update_yt_dlp(yt_dlp_path)

    try:
        video = await download_video(yt_dlp_path, url)

        await context.bot.send_video(
            chat_id=message.chat_id,
            video=io.BytesIO(video),
            filename="download.mp4",
            supports_streaming=True,
        )

        # remove the reactions from the command
        await context.bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[],
        )


    except Exception as e:
        print("ERROR DOWNLOADING VIDEO: ", e)
        await context.bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction="👎",
        )




def main():

    if len(sys.argv) != 2:
        print("Usage:\npython3 main.py [path to yt-dlp]")
        exit(1)

    yt_dlp_path = sys.argv[1]

    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    if not BOT_TOKEN:
        print("Put telegram bot token in .env")
        exit(1)

    app = Application.builder().token(BOT_TOKEN).build()

    app.bot_data["yt_dlp_path"] = yt_dlp_path

    app.add_handler(CommandHandler("get", get))

    print("Bot running")
    app.run_polling()


if __name__ == "__main__":
    main()
