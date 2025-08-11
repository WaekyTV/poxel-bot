# Fichier: bot.py

import os
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask

# --- Initialisation de Firebase et du bot ---
# 1. Obtenez les identifiants de votre compte de service Firebase.
#    - Allez dans la console Firebase -> Paramètres du projet -> Comptes de service.
#    - Générez une nouvelle clé privée et téléchargez le fichier JSON.
# 2. Sauvegardez le contenu du fichier JSON dans une variable d'environnement sur Render.
#    Appelez la variable FIREBASE_CREDENTIALS_JSON.
#    Pour cela, copiez le contenu du JSON, puis définissez la variable d'environnement avec cette valeur.

# Vérifie si la variable d'environnement existe
firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
if firebase_creds_json:
    # Sauvegarde temporairement les identifiants dans un fichier pour firebase_admin
    with open('firebase_creds.json', 'w') as f:
        f.write(firebase_creds_json)

    # Initialise l'application Firebase
    cred = credentials.Certificate('firebase_creds.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase a été initialisé avec succès.")
else:
    print("Erreur: La variable d'environnement 'FIREBASE_CREDENTIALS_JSON' n'est pas définie.")
    print("Le bot ne pourra pas se connecter à Firebase.")
    db = None

# Configure l'intention du bot pour les membres, les messages et les réactions
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Initialise le bot avec le préfixe de commande '!'
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Serveur Flask pour le ping Uptime Robot ---
# Ceci est nécessaire pour que Render garde le bot en vie.
app = Flask(__name__)

@app.route('/')
def home():
    """Un simple endpoint pour que le robot Uptime puisse pinguer."""
    return "Le bot Discord est en vie !"

# --- Fonctions utilitaires ---
def parse_duration(duration_str):
    """
    Analyse une chaîne de temps (ex: '1h30m15s') et la convertit en timedelta.
    Retourne un objet timedelta ou None en cas d'erreur.
    """
    total_seconds = 0
    current_number = ""
    for char in duration_str:
        if char.isdigit():
            current_number += char
        else:
            if current_number:
                value = int(current_number)
                if char == 'h':
                    total_seconds += value * 3600
                elif char == 'm':
                    total_seconds += value * 60
                elif char == 's':
                    total_seconds += value
                current_number = ""
    return timedelta(seconds=total_seconds) if total_seconds > 0 else None

# --- Événements du bot ---
@bot.event
async def on_ready():
    """Se déclenche lorsque le bot est prêt."""
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Le bot est prêt à démarrer...')
    # Démarre la tâche de vérification des événements expirés
    if db:
        check_expired_events.start()

# --- Commandes du bot ---
@bot.command(name='create_event')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, duration: str, role: discord.Role, *, description: str):
    """
    Crée un nouvel événement.
    Syntaxe: !create_event <durée> <@rôle> <description>
    Exemple: !create_event 2h30m @Participants Soirée Gaming!
    """
    if not db:
        await ctx.send("Erreur: La base de données n'est pas connectée. Veuillez vérifier les identifiants Firebase.")
        return

    # Analyse la durée
    event_duration = parse_duration(duration)
    if not event_duration:
        await ctx.send("Format de durée invalide. Utilisez le format '1h30m' (heures, minutes, secondes).")
        return

    # Calcule l'heure de fin
    end_time = datetime.utcnow() + event_duration
    
    # Crée un message d'événement
    event_message = await ctx.send(
        f"**Nouvel Événement: {description}**\n"
        f"Durée: {duration}\n"
        f"Inscrivez-vous en utilisant la commande `!join_event {ctx.message.id}`\n"
        f"Ce rôle (@{role.name}) sera supprimé automatiquement après {duration}."
    )

    # Sauvegarde l'événement dans Firebase
    event_data = {
        'message_id': str(event_message.id),
        'guild_id': str(ctx.guild.id),
        'role_id': str(role.id),
        'end_time': end_time,
        'participants': []
    }
    
    doc_ref = db.collection('events').document(str(event_message.id))
    doc_ref.set(event_data)
    
    await ctx.send(f"Événement créé! ID de l'événement: `{event_message.id}`")

@bot.command(name='join_event')
async def join_event(ctx, event_id: str):
    """
    Rejoint un événement existant et attribue le rôle temporaire.
    Syntaxe: !join_event <ID_de_l'événement>
    """
    if not db:
        await ctx.send("Erreur: La base de données n'est pas connectée. Veuillez vérifier les identifiants Firebase.")
        return
        
    doc_ref = db.collection('events').document(event_id)
    doc = doc_ref.get()

    if not doc.exists:
        await ctx.send("Cet événement n'existe pas ou est déjà terminé.")
        return

    data = doc.to_dict()
    guild = bot.get_guild(int(data['guild_id']))
    member = ctx.author

    if str(member.id) in data['participants']:
        await ctx.send(f"{member.mention}, vous êtes déjà inscrit à cet événement.")
        return

    # Attribue le rôle au membre
    role = guild.get_role(int(data['role_id']))
    if not role:
        await ctx.send("Le rôle associé à cet événement n'existe plus.")
        return
        
    await member.add_roles(role)
    
    # Ajoute le participant à la liste dans Firebase
    data['participants'].append(str(member.id))
    doc_ref.update({'participants': data['participants']})
    
    await ctx.send(f"{member.mention} a rejoint l'événement. Le rôle **{role.name}** vous a été attribué temporairement.")
    
@bot.command(name='end_event')
@commands.has_permissions(manage_roles=True)
async def end_event(ctx, event_id: str):
    """
    Termine manuellement un événement et supprime les rôles.
    Syntaxe: !end_event <ID_de_l'événement>
    """
    if not db:
        await ctx.send("Erreur: La base de données n'est pas connectée. Veuillez vérifier les identifiants Firebase.")
        return

    doc_ref = db.collection('events').document(event_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        await ctx.send("Cet événement n'existe pas.")
        return

    data = doc.to_dict()
    guild = bot.get_guild(int(data['guild_id']))
    role = guild.get_role(int(data['role_id']))
    
    if role:
        for participant_id in data['participants']:
            member = guild.get_member(int(participant_id))
            if member:
                await member.remove_roles(role)
    
    doc_ref.delete()
    await ctx.send(f"L'événement `{event_id}` a été terminé et les rôles ont été supprimés.")


# --- Tâche de fond pour vérifier les événements expirés ---
@tasks.loop(minutes=1)
async def check_expired_events():
    """
    Vérifie toutes les minutes s'il y a des événements expirés
    et supprime les rôles et les événements de Firebase.
    """
    print("Vérification des événements expirés...")
    events_ref = db.collection('events')
    
    # Requête pour les événements dont l'heure de fin est passée
    query = events_ref.where('end_time', '<', datetime.utcnow())
    
    docs = query.stream()
    
    for doc in docs:
        event_data = doc.to_dict()
        event_id = doc.id
        guild = bot.get_guild(int(event_data['guild_id']))
        role = guild.get_role(int(event_data['role_id']))
        
        if role:
            for participant_id in event_data['participants']:
                member = guild.get_member(int(participant_id))
                if member:
                    print(f"Suppression du rôle '{role.name}' pour le membre '{member.name}'.")
                    try:
                        await member.remove_roles(role)
                    except discord.Forbidden:
                        print("Erreur: Permissions insuffisantes pour supprimer le rôle.")
        
        # Supprime l'événement de la base de données
        doc.reference.delete()
        print(f"Événement `{event_id}` expiré et supprimé.")
        
# --- Point d'entrée principal ---
# Exécute à la fois le bot Discord et le serveur Flask
async def main():
    """Point d'entrée pour exécuter le bot et le serveur Flask."""
    discord_token = os.environ.get('DISCORD_TOKEN')
    if not discord_token:
        print("Erreur: La variable d'environnement 'DISCORD_TOKEN' n'est pas définie.")
        return

    # Crée un objet pour le processus Flask
    server_process = asyncio.create_task(asyncio.to_thread(lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))))
    
    # Démarre le bot Discord
    await bot.start(discord_token)
    
    # Attend la fin du serveur Flask (ne devrait pas se produire en temps normal)
    await server_process

if __name__ == '__main__':
    asyncio.run(main())

