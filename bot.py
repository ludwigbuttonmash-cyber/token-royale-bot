import os
import time
import traceback
import asyncio
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- SAFE GLOBAL ERROR HANDLER ----------------

@bot.event
async def on_error(event, *args, **kwargs):
    print("GLOBAL ERROR:")
    traceback.print_exc()

@bot.tree.error
async def on_app_command_error(interaction, error):
    print("APP COMMAND ERROR:")
    traceback.print_exception(type(error), error, error.__traceback__)

    try:
        if interaction.response.is_done():
            await interaction.followup.send("❌ Error occurred.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Error occurred.", ephemeral=True)
    except:
        pass

# ---------------- SAFE STARTUP ----------------

@bot.event
async def setup_hook():
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception:
        print("SYNC FAILED:")
        traceback.print_exc()

# ---------------- AUTO RECONNECT LOOP ----------------

async def run_bot():
    retry_delay = 5

    while True:
        try:
            print("Starting bot...")
            await bot.start(TOKEN)

        except discord.LoginFailure:
            print("INVALID TOKEN - STOPPING")
            break

        except Exception as e:
            print("BOT CRASHED:")
            traceback.print_exc()

            print(f"Restarting in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)

            # exponential backoff (max 60s)
            retry_delay = min(retry_delay * 2, 60)

# ---------------- ENTRY POINT ----------------

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("Bot stopped manually.")
