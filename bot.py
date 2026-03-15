import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os

TOKEN = os.environ.get("DISCORD_TOKEN")
API_URL = os.environ.get("EON_API_URL", "https://web-production-f655c.up.railway.app")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

COR_GOLD  = 0xf5c400
COR_RED   = 0xe8162a
COR_BLUE  = 0x1a3a8f
COR_GREEN = 0x1a8f4a
COR_INK   = 0x0a0a0f

sessions = {}

def get_session(user_id):
    return sessions.get(str(user_id))

def set_session(user_id, nick, password):
    sessions[str(user_id)] = {"nick": nick, "password": password}

def clear_session(user_id):
    sessions.pop(str(user_id), None)

async def api_post(path, body):
    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL + path, json=body) as r:
            return await r.json()

async def api_get(path):
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL + path) as r:
            return await r.json()

def auth_body(user_id, extra={}):
    s = get_session(user_id)
    if not s:
        return None
    return {"nick": s["nick"], "password": s["password"], **extra}

def not_logged_embed():
    e = discord.Embed(
        title="❌ Não logado!",
        description="Use `/login` para entrar ou `/register` para criar uma conta.",
        color=COR_RED
    )
    return e

@bot.event
async def on_ready():
    print(f"☄️ EON Bot online como {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Sincronizados {len(synced)} comandos")
    except Exception as e:
        print(f"Erro ao sincronizar: {e}")

# ── CONTA ──────────────────────────────────────────────────

@bot.tree.command(name="register", description="Criar uma conta no EON")
@app_commands.describe(nick="Seu nick de jogador", senha="Sua senha")
async def register(interaction: discord.Interaction, nick: str, senha: str):
    await interaction.response.defer(ephemeral=True)
    try:
        data = await api_post("/register", {"nick": nick.lower(), "password": senha})
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="✅ Conta criada!", description=f"Bem-vindo ao EON, **{nick}**!\nUse `/login` para entrar.", color=COR_GREEN)
        await interaction.followup.send(embed=e, ephemeral=True)
    except:
        await interaction.followup.send("Erro ao conectar à API.", ephemeral=True)

@bot.tree.command(name="login", description="Entrar na sua conta EON")
@app_commands.describe(nick="Seu nick", senha="Sua senha")
async def login(interaction: discord.Interaction, nick: str, senha: str):
    await interaction.response.defer(ephemeral=True)
    try:
        data = await api_post("/login", {"nick": nick.lower(), "password": senha})
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            set_session(interaction.user.id, nick.lower(), senha)
            e = discord.Embed(title="☄️ Login realizado!", color=COR_GOLD)
            e.add_field(name="Jogador", value=f"**{nick}** · {data.get('title','Novato')}", inline=False)
            e.add_field(name="💰 Carteira", value=str(data.get("balance", 0)), inline=True)
            e.add_field(name="🏦 Banco", value=str(data.get("bank", 0)), inline=True)
            e.add_field(name="⚡ Nível", value=f"Lv.{data.get('level',1)} · {data.get('xp',0)} XP", inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)
    except:
        await interaction.followup.send("Erro ao conectar à API.", ephemeral=True)

@bot.tree.command(name="logout", description="Sair da conta EON")
async def logout(interaction: discord.Interaction):
    clear_session(interaction.user.id)
    e = discord.Embed(title="👋 Até logo!", description="Você saiu da sua conta.", color=COR_INK)
    await interaction.response.send_message(embed=e, ephemeral=True)

# ── STATUS ─────────────────────────────────────────────────

@bot.tree.command(name="balance", description="Ver seu saldo")
async def balance(interaction: discord.Interaction):
    await interaction.response.defer()
    body = auth_body(interaction.user.id)
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/balance", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title=f"💰 Saldo de {data['nick']}", color=COR_GOLD)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
            e.add_field(name="Banco", value=f"**{data['bank']}** coins", inline=True)
            e.add_field(name="Total", value=f"**{data['balance']+data['bank']}** coins", inline=True)
            e.add_field(name="Nível", value=f"Lv.{data.get('level',1)}", inline=True)
            e.add_field(name="Título", value=data.get('title','Novato'), inline=True)
            e.add_field(name="XP", value=f"{data.get('xp',0)} XP", inline=True)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── AÇÕES ──────────────────────────────────────────────────

@bot.tree.command(name="work", description="Trabalhar para ganhar coins (cooldown 30min)")
async def work(interaction: discord.Interaction):
    await interaction.response.defer()
    body = auth_body(interaction.user.id)
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/work", body)
        if data.get("error"):
            e = discord.Embed(title="⏳ Cooldown", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="💼 GRIND!!", color=COR_GOLD)
            e.add_field(name="Ganhou", value=f"+**{data['earned']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
            e.add_field(name="+XP", value=f"+{data.get('xp_gain',0)} XP", inline=True)
            if data.get("leveled_up"):
                e.add_field(name="⬆️ LEVEL UP!", value=f"Nível **{data['level']}** · {data.get('title','')}", inline=False)
            if data.get("quest_rewards"):
                for q in data["quest_rewards"]:
                    e.add_field(name="✅ Quest completa!", value=f"{q['quest']} · +{q['reward']} coins", inline=False)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

@bot.tree.command(name="daily", description="Coletar recompensa diária")
async def daily(interaction: discord.Interaction):
    await interaction.response.defer()
    body = auth_body(interaction.user.id)
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/daily", body)
        if data.get("error"):
            e = discord.Embed(title="⏳ Cooldown", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="🎁 BONUS!!", color=COR_GREEN)
            e.add_field(name="Recompensa", value=f"+**{data['reward']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
            e.add_field(name="+XP", value=f"+{data.get('xp_gain',0)} XP", inline=True)
            if data.get("leveled_up"):
                e.add_field(name="⬆️ LEVEL UP!", value=f"Nível **{data['level']}** · {data.get('title','')}", inline=False)
            if data.get("quest_rewards"):
                for q in data["quest_rewards"]:
                    e.add_field(name="✅ Quest!", value=f"{q['quest']} · +{q['reward']} coins", inline=False)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

@bot.tree.command(name="mine", description="Minerar para ganhar coins (cooldown 1h)")
async def mine(interaction: discord.Interaction):
    await interaction.response.defer()
    body = auth_body(interaction.user.id)
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/mine", body)
        if data.get("error"):
            e = discord.Embed(title="⏳ Cooldown", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="⛏️ KANG!!", color=COR_BLUE)
            e.add_field(name="Minerou", value=f"+**{data['earned']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
            e.add_field(name="+XP", value=f"+{data.get('xp_gain',0)} XP", inline=True)
            if data.get("leveled_up"):
                e.add_field(name="⬆️ LEVEL UP!", value=f"Nível **{data['level']}** · {data.get('title','')}", inline=False)
            if data.get("quest_rewards"):
                for q in data["quest_rewards"]:
                    e.add_field(name="✅ Quest!", value=f"{q['quest']} · +{q['reward']} coins", inline=False)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

@bot.tree.command(name="crime", description="Cometer um crime (cooldown 1h, risco de multa)")
async def crime(interaction: discord.Interaction):
    await interaction.response.defer()
    body = auth_body(interaction.user.id)
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/crime", body)
        if data.get("error"):
            e = discord.Embed(title="⏳ Cooldown", description=data["error"], color=COR_RED)
        elif data.get("result") == "preso":
            e = discord.Embed(title="🚔 BUSTED!!", description="Você foi preso!", color=COR_RED)
            e.add_field(name="Multa", value=f"-**{data['fine']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
        else:
            e = discord.Embed(title="😈 HEIST!!", description="Crime bem sucedido!", color=COR_GREEN)
            e.add_field(name="Ganhou", value=f"+**{data['earned']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
            e.add_field(name="+XP", value=f"+{data.get('xp_gain',0)} XP", inline=True)
            if data.get("leveled_up"):
                e.add_field(name="⬆️ LEVEL UP!", value=f"Nível **{data['level']}** · {data.get('title','')}", inline=False)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── PVP ────────────────────────────────────────────────────

@bot.tree.command(name="rob", description="Roubar outro jogador")
@app_commands.describe(nick="Nick da vítima")
async def rob(interaction: discord.Interaction, nick: str):
    await interaction.response.defer()
    body = auth_body(interaction.user.id, {"target": nick.lower()})
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/rob", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        elif data.get("result") == "sucesso":
            e = discord.Embed(title="🔪 STOLEN!!", color=COR_GREEN)
            e.add_field(name="Vítima", value=nick, inline=True)
            e.add_field(name="Roubou", value=f"+**{data['stolen']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
        else:
            e = discord.Embed(title="🚔 CAUGHT!!", description="Tentativa falhou!", color=COR_RED)
            e.add_field(name="Multa", value=f"-**{data['fine']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── BANCO ──────────────────────────────────────────────────

@bot.tree.command(name="deposit", description="Depositar coins no banco")
@app_commands.describe(valor="Quantidade a depositar")
async def deposit(interaction: discord.Interaction, valor: int):
    await interaction.response.defer()
    body = auth_body(interaction.user.id, {"amount": valor})
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/deposit", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="🏦 SAVED!!", color=COR_BLUE)
            e.add_field(name="Depositou", value=f"**{data['deposited']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
            e.add_field(name="Banco", value=f"**{data['bank']}** coins", inline=True)
            if data.get("quest_rewards"):
                for q in data["quest_rewards"]:
                    e.add_field(name="✅ Quest!", value=f"{q['quest']} · +{q['reward']} coins", inline=False)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

@bot.tree.command(name="withdraw", description="Sacar coins do banco")
@app_commands.describe(valor="Quantidade a sacar")
async def withdraw(interaction: discord.Interaction, valor: int):
    await interaction.response.defer()
    body = auth_body(interaction.user.id, {"amount": valor})
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/withdraw", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="💸 CASH!!", color=COR_GOLD)
            e.add_field(name="Sacou", value=f"**{data['withdrawn']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
            e.add_field(name="Banco", value=f"**{data['bank']}** coins", inline=True)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

@bot.tree.command(name="transfer", description="Transferir coins para outro jogador")
@app_commands.describe(nick="Nick do destinatário", valor="Quantidade a transferir")
async def transfer(interaction: discord.Interaction, nick: str, valor: int):
    await interaction.response.defer()
    body = auth_body(interaction.user.id, {"target": nick.lower(), "amount": valor})
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/transfer", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="📤 SENT!!", color=COR_GREEN)
            e.add_field(name="Para", value=nick, inline=True)
            e.add_field(name="Enviou", value=f"**{valor}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['seu_saldo']}** coins", inline=True)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── LOJA ───────────────────────────────────────────────────

@bot.tree.command(name="shop", description="Ver itens da loja")
async def shop(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        data = await api_get("/shop")
        e = discord.Embed(title="🛒 LOJA EON", color=COR_GOLD)
        icons = {"espada":"⚔️","escudo":"🛡️","pocao":"🧪","picareta":"⛏️"}
        for name, info in data["items"].items():
            e.add_field(
                name=f"{icons.get(name,'📦')} {name.upper()} · {info['price']} coins",
                value=info["description"], inline=False
            )
        e.set_footer(text="Use /buy <item> para comprar")
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

@bot.tree.command(name="buy", description="Comprar um item da loja")
@app_commands.describe(item="Nome do item (espada, escudo, pocao, picareta)")
async def buy(interaction: discord.Interaction, item: str):
    await interaction.response.defer()
    body = auth_body(interaction.user.id, {"item": item.lower()})
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/buy", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            icons = {"espada":"⚔️","escudo":"🛡️","pocao":"🧪","picareta":"⛏️"}
            e = discord.Embed(title=f"GOT IT!! {icons.get(item,'📦')}", color=COR_GREEN)
            e.add_field(name="Comprou", value=item.upper(), inline=True)
            e.add_field(name="Pagou", value=f"**{data['price']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

@bot.tree.command(name="inventory", description="Ver seu inventário")
async def inventory(interaction: discord.Interaction):
    await interaction.response.defer()
    body = auth_body(interaction.user.id)
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/inventory", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title=f"🎒 Mochila de {data['nick']}", color=COR_BLUE)
            icons = {"espada":"⚔️","escudo":"🛡️","pocao":"🧪","picareta":"⛏️"}
            if not data["inventory"]:
                e.description = "Mochila vazia! Use `/shop` para ver os itens."
            else:
                for name, info in data["inventory"].items():
                    e.add_field(name=f"{icons.get(name,'📦')} {name.upper()}", value=info["description"], inline=True)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── SLOTS ──────────────────────────────────────────────────

@bot.tree.command(name="slots", description="Jogar slots")
@app_commands.describe(aposta="Quantidade a apostar")
async def slots(interaction: discord.Interaction, aposta: int):
    await interaction.response.defer()
    body = auth_body(interaction.user.id, {"bet": aposta})
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/slots", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            em = {"cereja":"🍒","limao":"🍋","sino":"🔔","estrela":"⭐","diamante":"💎"}
            reels = " · ".join([em.get(r, r) for r in data["reels"]])
            resultado = data["result"]
            cor = COR_GOLD if resultado == "JACKPOT!" else COR_GREEN if resultado == "ganhou!" else COR_RED
            e = discord.Embed(title=f"🎰 {resultado.upper()}", color=cor)
            e.add_field(name="Resultado", value=reels, inline=False)
            e.add_field(name="Aposta", value=f"**{aposta}** coins", inline=True)
            e.add_field(name="Ganhos", value=f"**{data['winnings']}** coins", inline=True)
            e.add_field(name="Carteira", value=f"**{data['balance']}** coins", inline=True)
            if data.get("leveled_up"):
                e.add_field(name="⬆️ LEVEL UP!", value=f"Nível **{data['level']}**", inline=False)
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── QUESTS ─────────────────────────────────────────────────

@bot.tree.command(name="quests", description="Ver suas missões diárias")
async def quests(interaction: discord.Interaction):
    await interaction.response.defer()
    body = auth_body(interaction.user.id)
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/quests", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="📜 MISSÕES DIÁRIAS", color=COR_BLUE)
            e.set_footer(text="Resetam à meia-noite")
            for q in data["quests"]:
                status = "✅" if q["done"] else "⬜"
                progress = f"{q['current']}/{q['target']}"
                e.add_field(
                    name=f"{status} {q['desc']}",
                    value=f"Progresso: **{progress}** · Recompensa: **+{q['reward']}** coins",
                    inline=False
                )
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── LEADERBOARD ────────────────────────────────────────────

@bot.tree.command(name="leaderboard", description="Ver o top 10 de jogadores")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        data = await api_get("/leaderboard")
        e = discord.Embed(title="🏆 LEADERBOARD EON", color=COR_GOLD)
        medals = ["👑", "🥈", "🥉"]
        for i, p in enumerate(data["leaderboard"]):
            rank = medals[i] if i < 3 else f"**{i+1}.**"
            e.add_field(
                name=f"{rank} {p['nick']} · {p.get('title','Novato')}",
                value=f"**{p['total']}** coins · Lv.{p.get('level',1)}",
                inline=False
            )
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── CHAT ───────────────────────────────────────────────────

@bot.tree.command(name="chat", description="Ver o chat global do EON")
async def chat(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        data = await api_get("/chat/messages")
        msgs = data.get("messages", [])[-10:]
        e = discord.Embed(title="💬 CHAT GLOBAL EON", color=COR_BLUE)
        if not msgs:
            e.description = "Nenhuma mensagem ainda."
        else:
            text = ""
            for m in msgs:
                text += f"**{m['nick']}**: {m['message']}\n"
            e.description = text
        e.set_footer(text="Use /say para enviar uma mensagem")
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

@bot.tree.command(name="say", description="Enviar mensagem no chat global")
@app_commands.describe(mensagem="Sua mensagem")
async def say(interaction: discord.Interaction, mensagem: str):
    await interaction.response.defer()
    body = auth_body(interaction.user.id, {"message": mensagem})
    if not body:
        await interaction.followup.send(embed=not_logged_embed(), ephemeral=True); return
    try:
        data = await api_post("/chat/send", body)
        if data.get("error"):
            e = discord.Embed(title="❌ Erro", description=data["error"], color=COR_RED)
        else:
            e = discord.Embed(title="💬 Mensagem enviada!", color=COR_GREEN)
            e.description = f"**{get_session(interaction.user.id)['nick']}**: {mensagem}"
        await interaction.followup.send(embed=e)
    except:
        await interaction.followup.send("Erro ao conectar à API.")

# ── AJUDA ──────────────────────────────────────────────────

@bot.tree.command(name="help", description="Ver todos os comandos do EON")
async def help(interaction: discord.Interaction):
    e = discord.Embed(title="☄️ EON — Comandos", color=COR_GOLD)
    e.add_field(name="👤 Conta", value="`/register` `/login` `/logout`", inline=False)
    e.add_field(name="💰 Status", value="`/balance` `/inventory`", inline=False)
    e.add_field(name="⚡ Ações", value="`/work` `/daily` `/mine` `/crime`", inline=False)
    e.add_field(name="🗡️ PVP", value="`/rob <nick>`", inline=False)
    e.add_field(name="🏦 Banco", value="`/deposit` `/withdraw` `/transfer`", inline=False)
    e.add_field(name="🛒 Loja", value="`/shop` `/buy <item>`", inline=False)
    e.add_field(name="🎰 Jogos", value="`/slots <aposta>`", inline=False)
    e.add_field(name="📜 Missões", value="`/quests`", inline=False)
    e.add_field(name="🏆 Ranking", value="`/leaderboard`", inline=False)
    e.add_field(name="💬 Chat", value="`/chat` `/say <mensagem>`", inline=False)
    e.set_footer(text="EON Economy Bot v4.0")
    await interaction.response.send_message(embed=e)

if __name__ == "__main__":
    bot.run(TOKEN)
