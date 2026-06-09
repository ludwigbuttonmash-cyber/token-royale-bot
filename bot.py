import discord
from discord.ext import commands
from discord import app_commands
import random
import aiosqlite
import asyncio
from datetime import datetime, timedelta

TOKEN = "MTUxMzg0NDE1OTk3MzI5NDExMA.GedcOA.d_CiPL02vNY7e3sf67-G07LMRIPQydZCHY12eg"

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB = "economy.db"

# ================= DATABASE =================

async def setup_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 1000,
            last_daily TEXT,
            streak INTEGER DEFAULT 0
        )
        """)
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
        await db.commit()

        async with db.execute(
            "SELECT balance, last_daily, streak FROM users WHERE user_id=?",
            (user_id,)
        ) as cur:
            return await cur.fetchone()

async def update_balance(user_id, amount):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        await db.commit()

async def set_daily(user_id, time_str, streak):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE users SET last_daily=?, streak=? WHERE user_id=?",
            (time_str, streak, user_id)
        )
        await db.commit()

# ================= CARDS =================

suits = ["♠", "♥", "♦", "♣"]
ranks = {
    "A": 11, "2": 2, "3": 3, "4": 4,
    "5": 5, "6": 6, "7": 7, "8": 8,
    "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10
}

def deck():
    d = [(r, s) for s in suits for r in ranks]
    random.shuffle(d)
    return d

def value(hand):
    total = sum(ranks[c[0]] for c in hand)
    aces = sum(1 for c in hand if c[0] == "A")

    while total > 21 and aces:
        total -= 10
        aces -= 1

    return total

def txt(hand):
    return " ".join(f"{r}{s}" for r, s in hand)

# ================= GAME VIEW =================

class Blackjack(discord.ui.View):
    def __init__(self, player, bet, deck, ph, dh):
        super().__init__(timeout=120)

        self.player = player
        self.bet = bet
        self.deck = deck
        self.ph = ph
        self.dh = dh

        self.finished = False
        self.doubled = False
        self.split_used = False

    # -------- EMBED (ANIMATION STYLE A) --------

    def embed(self, reveal=False, status="Playing 🃏"):
        e = discord.Embed(
            title="🃏 Casino Blackjack",
            description=f"Bet: **{self.bet}** tokens",
            color=discord.Color.gold()
        )

        e.add_field(
            name="Your Hand",
            value=f"{txt(self.ph)}\nTotal: **{value(self.ph)}**",
            inline=False
        )

        if reveal:
            e.add_field(
                name="Dealer",
                value=f"{txt(self.dh)}\nTotal: **{value(self.dh)}**",
                inline=False
            )
        else:
            e.add_field(
                name="Dealer",
                value=f"{self.dh[0][0]}{self.dh[0][1]} ❓",
                inline=False
            )

        e.set_footer(text=status)
        return e

    async def interaction_check(self, interaction):
        return interaction.user.id == self.player.id

    # ================= END GAME =================

    async def end(self, interaction):

        if self.finished:
            return

        self.finished = True

        for c in self.children:
            c.disabled = True

        # DEALER ANIMATION (A feature)
        while value(self.dh) < 17:
            self.dh.append(self.deck.pop())
            await interaction.edit_original_response(
                embed=self.embed(True, "Dealer drawing... 🎬"),
                view=self
            )
            await asyncio.sleep(0.8)

        p = value(self.ph)
        d = value(self.dh)

        bet = self.bet * (2 if self.doubled else 1)

        # blackjack payout (C feature)
        if len(self.ph) == 2 and p == 21:
            bet = int(self.bet * 2.5)

        if p > 21:
            await update_balance(self.player.id, -bet)
            result, color = f"💥 Bust -{bet}", discord.Color.red()

        elif d > 21:
            await update_balance(self.player.id, bet)
            result, color = f"🎉 Dealer bust +{bet}", discord.Color.green()

        elif p > d:
            await update_balance(self.player.id, bet)
            result, color = f"🎉 Win +{bet}", discord.Color.green()

        elif p < d:
            await update_balance(self.player.id, -bet)
            result, color = f"😢 Lose -{bet}", discord.Color.red()

        else:
            result, color = "🤝 Push", discord.Color.light_grey()

        e = self.embed(True, result)
        e.color = color

        await interaction.edit_original_response(embed=e, view=self)

    # ================= BUTTONS =================

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction, button):

        if self.finished:
            return

        self.ph.append(self.deck.pop())

        await interaction.response.edit_message(
            embed=self.embed(status="Hit 🎴"),
            view=self
        )

        await asyncio.sleep(0.6)

        if value(self.ph) > 21:
            await self.end(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction, button):
        await interaction.response.defer()
        await self.end(interaction)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction, button):

        if len(self.ph) != 2:
            await interaction.response.send_message("Only first move!", ephemeral=True)
            return

        self.doubled = True
        self.ph.append(self.deck.pop())

        await interaction.response.edit_message(
            embed=self.embed(status="Double Down 🔥"),
            view=self
        )

        await asyncio.sleep(0.6)

        await self.end(interaction)

# ================= COMMANDS =================

@bot.tree.command(name="blackjack")
async def blackjack(interaction: discord.Interaction, bet: int):

    bal, _, _ = await get_user(interaction.user.id)

    if bet <= 0:
        return await interaction.response.send_message("Invalid bet", ephemeral=True)

    if bet > bal:
        return await interaction.response.send_message("Not enough tokens", ephemeral=True)

    d = deck()
    ph = [d.pop(), d.pop()]
    dh = [d.pop(), d.pop()]

    view = Blackjack(interaction.user, bet, d, ph, dh)

    await interaction.response.send_message(embed=view.embed(), view=view)

# ================= DAILY (B FEATURE) =================

@bot.tree.command(name="daily")
async def daily(interaction: discord.Interaction):

    bal, last, streak = await get_user(interaction.user.id)

    now = datetime.utcnow()

    if last:
        last_time = datetime.fromisoformat(last)
        if now - last_time < timedelta(hours=24):
            return await interaction.response.send_message("Already claimed daily.", ephemeral=True)

        if now - last_time < timedelta(hours=48):
            streak += 1
        else:
            streak = 1
    else:
        streak = 1

    reward = 500 + (streak * 100)

    await update_balance(interaction.user.id, reward)
    await set_daily(interaction.user.id, now.isoformat(), streak)

    await interaction.response.send_message(
        f"🎁 Daily +{reward} tokens (Streak {streak})"
    )

# ================= PING =================

@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong 🏓")

# ================= STARTUP =================

@bot.event
async def setup_hook():
    await bot.tree.sync()

@bot.event
async def on_ready():
    await setup_db()
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)