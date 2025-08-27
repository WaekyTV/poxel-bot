import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import datetime
import asyncio
import os
import json
import pytz
from flask import Flask
from threading import Thread

# Configuration du bot
intents = discord.Intents.all()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.reactions = True

BOT_PREFIX = "!"
NEON_PURPLE = 0x6441a5
NEON_BLUE = 0x027afa
USER_TIMEZONE = pytz.timezone('Europe/Paris')
SERVER_TIMEZONE = pytz.utc
DATABASE_FILE = 'events.json'

def load_events():
    """Charge les données des événements depuis le fichier."""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_events(data):
    """Sauvegarde les données des événements dans le fichier."""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

db = load_events()
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# Configuration de Flask pour l'hébergement
app = Flask(__name__)

@app.route('/')
def home():
    return "Poxel Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

async def update_event_embed(bot, event_name):
    """Met à jour l'embed de l'événement en temps réel."""
    event_data = db['events'].get(event_name)
    if not event_data:
        return

    channel_id = event_data['announcement_channel_id']
    message_id = event_data['message_id']
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = await bot.fetch_channel(channel_id)

        message = await channel.fetch_message(message_id)

        # Récupère la liste des participants
        participants_count = len(event_data.get('participants', []))

        # Met à jour le footer avec le nombre de participants
        embed = message.embeds[0]
        embed.set_footer(text=f"Participants: {participants_count}")
        await message.edit(embed=embed)
    except discord.NotFound:
        print(f"Message ou canal non trouvé pour l'événement '{event_name}'.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'embed: {e}")

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('------')
    check_events.start()
    await bot.change_presence(activity=discord.Game(name="!helpoxel pour de l'aide"))

@bot.event
async def on_reaction_add(reaction, user):
    """Gère les réactions pour rejoindre un événement."""
    if user.bot:
        return

    message_id = reaction.message.id
    for event_name, event_data in db['events'].items():
        if event_data['message_id'] == message_id:
            user_id = user.id
            if not any(p['id'] == user_id for p in event_data['participants']):
                event_data['participants'].append({'id': user_id, 'username': str(user)})
                save_events(db)
                await reaction.message.channel.send(f"{user.mention} a rejoint l'événement **{event_name}** !", delete_after=5)
                await update_event_embed(bot, event_name)
            break

@bot.event
async def on_reaction_remove(reaction, user):
    """Gère les réactions pour quitter un événement."""
    if user.bot:
        return

    message_id = reaction.message.id
    for event_name, event_data in db['events'].items():
        if event_data['message_id'] == message_id:
            user_id = user.id
            event_data['participants'] = [p for p in event_data['participants'] if p['id'] != user_id]
            save_events(db)
            await reaction.message.channel.send(f"{user.mention} a quitté l'événement **{event_name}**.", delete_after=5)
            await update_event_embed(bot, event_name)
            break

@tasks.loop(minutes=1)
async def check_events():
    """Vérifie et gère les événements en cours ou terminés."""
    now_utc = datetime.datetime.now(SERVER_TIMEZONE)
    events_to_delete = []

    for event_name, event_data in db['events'].items():
        end_time_utc = datetime.datetime.fromisoformat(event_data['end_time_utc'])
        start_time_utc = datetime.datetime.fromisoformat(event_data['start_time_utc'])

        # Gère le début de l'événement
        if now_utc >= start_time_utc and not event_data.get('is_started'):
            db['events'][event_name]['is_started'] = True
            save_events(db)
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone L'événement **{event_name}** a commencé ! Bonne chance ! 🍀")

        # Gère la fin de l'événement
        if now_utc >= end_time_utc and event_data.get('is_started'):
            channel = bot.get_channel(event_data['announcement_channel_id'])
            if channel:
                await channel.send(f"@everyone L'événement **{event_name}** est maintenant terminé. Merci à tous les participants ! 🎉")
            
            for participant in event_data['participants']:
                member = bot.get_guild(channel.guild.id).get_member(participant['id'])
                if member:
                    try:
                        role = member.guild.get_role(event_data['role_id'])
                        if role and role in member.roles:
                            await member.remove_roles(role)
                    except Exception as e:
                        print(f"Impossible de retirer le rôle du membre {member.id}: {e}")
            
            try:
                message = await channel.fetch_message(event_data['message_id'])
                await message.delete()
            except discord.NotFound:
                pass

            events_to_delete.append(event_name)
        
        # Mise à jour de l'embed en temps réel
        await update_event_embed(bot, event_name)

    for event_name in events_to_delete:
        if event_name in db['events']:
            del db['events'][event_name]
        
    save_events(db)

@bot.command(name='helpoxel', aliases=['help'])
async def help_command(ctx):
    """Affiche un manuel d'aide pour le bot."""
    help_text = """
    **MANUEL DE POXEL**
    Bienvenue dans le manuel de Poxel. Voici la liste des commandes disponibles :
    
    `!tirage`
    Effectue un tirage au sort parmi les participants d'un événement.
    
    `!end_event`
    Termine un événement manuellement.
    
    `!helpoxel`
    Affiche une aide détaillée ou la liste des commandes.
    
    `!create_event`
    Crée un événement pour le jour même.
    Syntaxe: `!create_event 21h30 10min @role #annonce #salle 10 "pseudonyme" "nom_evenement"`
    
    `!create_event_plan`
    Crée un événement planifié pour une date future.
    Identique à `!create_event` mais avec une date en plus.
    Syntaxe: `!create_event_plan JJ/MM/AAAA 21h30 10min @role #annonce #salle 10 "pseudonyme" "nom_evenement"`
    """
    embed = discord.Embed(
        title="Manuel de Poxel",
        description=help_text,
        color=NEON_BLUE
    )
    await ctx.send(embed=embed)

@bot.command(name='create_event')
async def create_event(ctx, start_time, duration_str, role: discord.Role, announcement_channel: discord.TextChannel, voice_channel: discord.VoiceChannel, max_participants: int, pseudo: str, event_name: str):
    """Crée un événement pour le jour même."""
    
    if event_name in db['events']:
        await ctx.send("Un événement avec ce nom existe déjà. Veuillez en choisir un autre.")
        return

    try:
        now_paris = datetime.datetime.now(USER_TIMEZONE)
        
        # Parse la durée
        if duration_str.endswith('min'):
            duration_minutes = int(duration_str.replace('min', ''))
            event_duration = datetime.timedelta(minutes=duration_minutes)
        elif duration_str.endswith('h'):
            duration_hours = int(duration_str.replace('h', ''))
            event_duration = datetime.timedelta(hours=duration_hours)
        else:
            await ctx.send("Format de durée invalide. Utilisez '10min' ou '1h'.")
            return

        # Parse l'heure de début
        start_hour, start_minute = map(int, start_time.split('h'))
        start_datetime_paris = now_paris.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        
        # Si l'heure de début est passée pour aujourd'hui, ajoute un jour
        if start_datetime_paris < now_paris:
            start_datetime_paris += datetime.timedelta(days=1)
        
        # Convertir les heures de début et de fin en UTC
        start_datetime_utc = start_datetime_paris.astimezone(SERVER_TIMEZONE)
        end_datetime_utc = start_datetime_utc + event_duration

        if end_datetime_utc < now_paris.astimezone(SERVER_TIMEZONE):
             await ctx.send("L'heure de fin est déjà passée. Veuillez choisir une heure future.")
             return
             
    except ValueError:
        await ctx.send("Format de temps invalide. Utilisez '21h30'.")
        return

    # Création de l'embed
    embed = discord.Embed(
        title=f"🎉 Événement : {event_name}",
        description=f"Un événement a été créé par **{pseudo}** pour un tirage au sort !",
        color=NEON_PURPLE
    )
    embed.add_field(name="Heure de début", value=start_datetime_paris.strftime("%H:%M"), inline=True)
    embed.add_field(name="Durée", value=duration_str, inline=True)
    embed.add_field(name="Salon vocal", value=voice_channel.mention, inline=False)
    embed.add_field(name="Rôle requis pour l'inscription", value=role.mention, inline=False)
    embed.set_footer(text="Participants: 0")

    message = await announcement_channel.send(embed=embed)
    await message.add_reaction('✅')

    # Sauvegarde des données de l'événement
    db['events'][event_name] = {
        'message_id': message.id,
        'announcement_channel_id': announcement_channel.id,
        'voice_channel_id': voice_channel.id,
        'role_id': role.id,
        'max_participants': max_participants,
        'pseudo': pseudo,
        'start_time_utc': start_datetime_utc.isoformat(),
        'end_time_utc': end_datetime_utc.isoformat(),
        'is_started': False,
        'participants': []
    }
    save_events(db)

@bot.command(name='create_event_plan')
async def create_event_plan(ctx, date, start_time, duration_str, role: discord.Role, announcement_channel: discord.TextChannel, voice_channel: discord.VoiceChannel, max_participants: int, pseudo: str, event_name: str):
    """Crée un événement planifié pour une date future."""
    
    if event_name in db['events']:
        await ctx.send("Un événement avec ce nom existe déjà. Veuillez en choisir un autre.")
        return
        
    try:
        day, month, year = map(int, date.split('/'))
        start_hour, start_minute = map(int, start_time.split('h'))
        
        # Parse la durée
        if duration_str.endswith('min'):
            duration_minutes = int(duration_str.replace('min', ''))
            event_duration = datetime.timedelta(minutes=duration_minutes)
        elif duration_str.endswith('h'):
            duration_hours = int(duration_str.replace('h', ''))
            event_duration = datetime.timedelta(hours=duration_hours)
        else:
            await ctx.send("Format de durée invalide. Utilisez '10min' ou '1h'.")
            return
            
        start_datetime_paris = USER_TIMEZONE.localize(datetime.datetime(year, month, day, start_hour, start_minute))
        start_datetime_utc = start_datetime_paris.astimezone(SERVER_TIMEZONE)
        end_datetime_utc = start_datetime_utc + event_duration
        
        if start_datetime_utc < datetime.datetime.now(SERVER_TIMEZONE):
            await ctx.send("L'heure de début est déjà passée. Veuillez choisir une heure future.")
            return

    except ValueError:
        await ctx.send("Format de date ou de temps invalide. Utilisez 'JJ/MM/AAAA' et '21h30'.")
        return

    # Création de l'embed
    embed = discord.Embed(
        title=f"🎉 Événement Planifié : {event_name}",
        description=f"Un événement a été créé par **{pseudo}** pour un tirage au sort !",
        color=NEON_PURPLE
    )
    embed.add_field(name="Date", value=start_datetime_paris.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Heure de début", value=start_datetime_paris.strftime("%H:%M"), inline=True)
    embed.add_field(name="Durée", value=duration_str, inline=True)
    embed.add_field(name="Salon vocal", value=voice_channel.mention, inline=False)
    embed.add_field(name="Rôle requis pour l'inscription", value=role.mention, inline=False)
    embed.set_footer(text="Participants: 0")

    message = await announcement_channel.send(embed=embed)
    await message.add_reaction('✅')

    # Sauvegarde des données de l'événement
    db['events'][event_name] = {
        'message_id': message.id,
        'announcement_channel_id': announcement_channel.id,
        'voice_channel_id': voice_channel.id,
        'role_id': role.id,
        'max_participants': max_participants,
        'pseudo': pseudo,
        'start_time_utc': start_datetime_utc.isoformat(),
        'end_time_utc': end_datetime_utc.isoformat(),
        'is_started': False,
        'participants': []
    }
    save_events(db)

@bot.command(name='end_event')
async def end_event(ctx, event_name: str):
    """Termine un événement manuellement."""
    if event_name in db['events']:
        event_data = db['events'][event_name]
        event_data['end_time_utc'] = datetime.datetime.now(SERVER_TIMEZONE).isoformat()
        event_data['is_started'] = True  # Pour que la boucle le détecte et le supprime
        save_events(db)
        await ctx.send(f"L'événement **{event_name}** a été programmé pour se terminer sous peu.")
    else:
        await ctx.send(f"L'événement **{event_name}** n'existe pas.")

@bot.command(name='tirage')
async def tirage_event(ctx, event_name: str):
    """Effectue un tirage au sort parmi les participants d'un événement."""
    import random
    if event_name in db['events']:
        participants = db['events'][event_name].get('participants', [])
        if len(participants) > 0:
            winner = random.choice(participants)
            winner_user = bot.get_user(winner['id'])
            if winner_user:
                await ctx.send(f"Le gagnant du tirage au sort pour l'événement **{event_name}** est {winner_user.mention} ! Félicitations ! 🎉")
            else:
                await ctx.send(f"Le gagnant du tirage au sort pour l'événement **{event_name}** est **{winner['username']}** ! Félicitations ! �")
        else:
            await ctx.send("Il n'y a pas de participants pour cet événement.")
    else:
        await ctx.send(f"L'événement **{event_name}** n'existe pas.")


if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    bot.run(os.environ.get('DISCORD_BOT_TOKEN'))
�
