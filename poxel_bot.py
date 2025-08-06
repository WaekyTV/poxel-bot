import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
import re  # Pour parser la durée
import os  # Pour accéder aux variables d'environnement (le TOKEN)
import threading
from flask import Flask  # Ajouté pour le serveur web de Replit
import firebase_admin
from firebase_admin import credentials, firestore

# ==============================================================================
# === INSTRUCTIONS IMPORTANTES POUR REPLIT ===
# ==============================================================================
# 1. DÉPENDANCES : Assurez-vous que les bibliothèques suivantes sont installées
#    dans votre projet Replit :
#    - discord.py
#    - firebase-admin
#    - Flask
#    Vous pouvez les ajouter via le fichier 'pyproject.toml' ou en utilisant le
#    gestionnaire de paquets de Replit.
#
# 2. FICHIER FIREBASE : Placez le fichier 'serviceAccountKey.json' que vous
#    avez téléchargé depuis Firebase dans le même répertoire que ce script.
#
# 3. SECRETS REPLIT : Ajoutez votre TOKEN Discord dans les secrets de Replit.
#    - Cliquez sur 'Secrets' dans la barre latérale.
#    - Ajoutez une nouvelle clé nommée 'DISCORD_TOKEN'.
#    - Collez votre token dans le champ 'Value'.
# ==============================================================================

# --- Configuration du Bot ---
# Récupère le TOKEN depuis les variables d'environnement de Replit.
TOKEN = os.environ.get('DISCORD_TOKEN')

if not TOKEN:
    print("ERREUR : Le TOKEN Discord n'est pas configuré dans les secrets de Replit.")
    exit()

# --- Configuration Firebase ---
try:
    # Le fichier 'serviceAccountKey.json' doit être dans le même dossier que ce script.
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"ERREUR lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assurez-vous que 'serviceAccountKey.json' est présent et valide.")
    exit()

# Les "intents" sont les permissions que le bot demande à Discord.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True # Ajouté pour détecter les changements d'état vocal

# Initialisation du bot avec un préfixe de commande '!' et les intents spécifiés.
# Le help_command est désactivé pour que nous puissions créer notre propre commande d'aide.
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- Fonctions Utilitaires ---

def parse_duration(duration_str: str) -> int:
    """
    Parse une chaîne de durée (ex: "2h", "30m", "5s") en secondes.
    """
    total_seconds = 0
    matches = re.findall(r'(\d+)([hms])', duration_str.lower())

    if not matches:
        raise ValueError("Format de durée invalide. Utilisez '2h', '30m', '5s' ou une combinaison.")

    for value, unit in matches:
        value = int(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
    return total_seconds

async def _update_event_embed(guild, event_data, message_id):
    """
    Met à jour l'embed de l'événement avec les participants actuels.
    """
    text_channel = guild.get_channel(event_data['text_channel_id'])
    if not text_channel:
        return

    try:
        event_message = await text_channel.fetch_message(message_id)
        if not event_message:
            return

        embed = event_message.embeds[0]
        
        participants_mentions = []
        for user_id in event_data.get('participants', []):
            member = guild.get_member(user_id)
            if member:
                participants_mentions.append(member.mention)
        
        # Le champ des joueurs inscrits est maintenant mis à jour en temps réel
        players_field_value = "\n".join(participants_mentions) if participants_mentions else "*Aucun joueur inscrit pour le moment.*"

        # On met à jour le champ des joueurs
        embed.set_field_at(
            0, # Index 0 car c'est le premier champ de l'embed
            name=f"**Joueurs inscrits ({len(participants_mentions)} / {event_data['max_participants']})**",
            value=players_field_value,
            inline=False
        )

        await event_message.edit(embed=embed)

    except discord.NotFound:
        print(f"Message de la partie non trouvé pour la mise à jour : {message_id}")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de la partie : {e}")

# --- Événements du Bot ---

@bot.event
async def on_ready():
    """
    Se déclenche lorsque le bot est connecté à Discord et prêt.
    """
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les parties !')
    # Démarre la tâche de vérification des événements expirés
    check_expired_events.start()

@bot.event
async def on_command_error(ctx, error):
    """
    Gère les erreurs de commande pour une meilleure expérience utilisateur.
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"| ERREUR | ARGUMENT MANQUANT\n> `!{ctx.command.name} {ctx.command.usage}`", ephemeral=True)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"| ERREUR | ARGUMENT INVALIDE", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("| ERREUR | PERMISSION REFUSÉE", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass # Ignore les commandes qui n'existent pas
    else:
        print(f"Erreur de commande : {error}")
        await ctx.send(f"| ERREUR | INATTENDUE : `{error}`", ephemeral=True)

# --- Commandes du Bot ---

@bot.command(name='create_event', usage='<@rôle> <#salon_textuel> <durée (ex: 2h, 30m)> <max_participants> <étiquette_participants> <#salon_attente_vocal> <#salon_de_jeu_vocal> <Nom de la partie>')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, text_channel: discord.TextChannel, duration_str: str, max_participants: int, participant_label: str, waiting_room_channel: discord.VoiceChannel, destination_voice_channel: discord.VoiceChannel, *event_name_parts):
    """
    Crée une nouvelle partie avec un rôle temporaire, des salons et une durée.
    """
    event_name = " ".join(event_name_parts)
    if not event_name:
        await ctx.send("| ERREUR | NOM DE LA PARTIE MANQUANT", ephemeral=True)
        return

    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()
    if existing_event_docs:
        await ctx.send(f"| ERREUR | LA PARTIE '{event_name}' EXISTE DÉJÀ", ephemeral=True)
        return

    if max_participants <= 0:
        await ctx.send("| ERREUR | CAPACITÉ DE JOUEURS INVALIDE", ephemeral=True)
        return

    try:
        duration_seconds = parse_duration(duration_str)
    except ValueError as e:
        await ctx.send(f"| ERREUR | {str(e).upper()}", ephemeral=True)
        return

    end_time = datetime.now() + timedelta(seconds=duration_seconds)
    temp_message = await ctx.send(">>> Chargement de la partie...")

    event_data_firestore = {
        'name': event_name,
        'role_id': role.id,
        'text_channel_id': text_channel.id,
        'waiting_room_channel_id': waiting_room_channel.id,
        'destination_voice_channel_id': destination_voice_channel.id, # Ajout du salon de destination
        'end_time': end_time,
        'max_participants': max_participants,
        'participant_label': participant_label,
        'participants': [],
        'message_id': temp_message.id,
        'guild_id': ctx.guild.id
    }
    doc_ref = db.collection('events').add(event_data_firestore)
    event_firestore_id = doc_ref[1].id

    # Création des boutons avec le nouveau style rétro-futuriste
    view = discord.ui.View(timeout=None)
    start_button = discord.ui.Button(
        label="START", 
        style=discord.ButtonStyle.primary,
        custom_id=f"join_event_{event_firestore_id}",
        emoji="🎮"
    )
    leave_button = discord.ui.Button(
        label="EXIT", 
        style=discord.ButtonStyle.danger,
        custom_id=f"leave_event_{event_firestore_id}",
        emoji="🚪"
    )

    view.add_item(start_button)
    view.add_item(leave_button)

    # Création de l'embed avec le style "mix"
    embed = discord.Embed(
        title=f"NOUVELLE PARTIE : {event_name.upper()}",
        description=f"**Une nouvelle partie a été lancée ! Préparez-vous à jouer !**",
        color=discord.Color.from_rgb(255, 0, 154) # Rose néon
    )
    embed.add_field(name=f"**Joueurs inscrits (0 / {max_participants})**", value="*Aucun joueur inscrit pour le moment.*", inline=False)
    embed.add_field(name="**Rôle requis :**", value=f"{role.mention}", inline=True)
    embed.add_field(name="**Salon de jeu :**", value=f"{text_channel.mention}", inline=True)
    embed.add_field(name="**Durée :**", value=f"{duration_str} (Fin de partie <t:{int(end_time.timestamp())}:R>)", inline=False)
    embed.add_field(name="**Comment rejoindre ?**", value=f"1. Appuyez sur le bouton 'START'.\n2. Vous obtiendrez votre rôle et serez prêt à être déplacé vers le salon de jeu !", inline=False)
    embed.set_footer(text="| P.O.X.E.L | Appuyez sur START pour participer.", icon_url="https://images.emojiterra.com/google/noto-emoji/v2.034/512px/1f47d.png")
    embed.timestamp = datetime.now()

    await temp_message.edit(content=None, embed=embed, view=view)
    await ctx.send(f"| INFO | PARTIE '{event_name.upper()}' CRÉÉE", ephemeral=True)


async def _end_event(event_doc_id: str):
    """
    Fonction interne pour terminer un événement, retirer les rôles et nettoyer.
    """
    event_ref = db.collection('events').document(event_doc_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        print(f"Tentative de terminer une partie non existante dans Firestore : {event_doc_id}")
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = bot.get_guild(event_data['guild_id'])
    
    if not guild:
        print(f"Guilde non trouvée pour la partie {event_name} (ID: {event_doc_id})")
        event_ref.delete()
        return

    role = guild.get_role(event_data['role_id'])
    text_channel = guild.get_channel(event_data['text_channel_id'])

    all_participants = list(event_data.get('participants', []))
    for user_id in all_participants:
        member = guild.get_member(user_id)
        if member and role:
            try:
                await member.remove_roles(role, reason=f"Fin de la partie {event_name}")
                print(f"Rôle {role.name} retiré à {member.display_name} pour la partie {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")

    event_ref.delete()
    print(f"Partie '{event_name}' (ID: {event_doc_id}) supprimée de Firestore.")

    if text_channel:
        try:
            await text_channel.send(f"| ALERTE | FIN DE PARTIE : '{event_name.upper()}'")
        except discord.Forbidden:
            print(f"Permissions insuffisantes pour envoyer un message dans le salon {text_channel.name}")
    else:
        print(f"Salon de la partie {event_name} non trouvé.")

    try:
        event_message = await text_channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = event_message.embeds[0]
            embed.color = discord.Color.from_rgb(0, 158, 255) # Bleu
            embed.title = f"PARTIE TERMINÉE : {event_name.upper()}"
            embed.description = f"**La partie est terminée. Bien joué !**"
            embed.clear_fields()
            embed.add_field(name="**Score final :**", value=f"{len(event_data.get('participants', []))} / {event_data['max_participants']} {event_data['participant_label']}", inline=False)
            await event_message.edit(embed=embed, view=None)
    except discord.NotFound:
        print(f"Message de la partie {event_name} (ID: {event_doc_id}) non trouvé sur Discord. Il a peut-être été supprimé manuellement.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de la partie : {e}")


@bot.command(name='end_event', usage='<Nom de la partie>')
@commands.has_permissions(manage_roles=True)
async def end_event_command(ctx, *event_name_parts):
    """
    Termine manuellement un événement et retire les rôles aux participants.
    """
    event_name = " ".join(event_name_parts)
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        await ctx.send(f"| ERREUR | LA PARTIE '{event_name.upper()}' N'EXISTE PAS", ephemeral=True)
        return

    event_doc_id = existing_event_docs[0].id
    
    await ctx.send(f">>> Fin de la partie '{event_name.upper()}' en cours...", ephemeral=True)
    await _end_event(event_doc_id)
    await ctx.send(f"| INFO | PARTIE '{event_name.upper()}' TERMINÉE MANUELLEMENT", ephemeral=True)


@bot.command(name='move_participants', usage='<Nom de la partie>')
@commands.has_permissions(move_members=True)
async def move_participants(ctx, *event_name_parts):
    """
    Déplace tous les participants d'une partie vers le salon de jeu.
    """
    event_name = " ".join(event_name_parts)
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        await ctx.send(f"| ERREUR | LA PARTIE '{event_name.upper()}' N'EXISTE PAS", ephemeral=True)
        return

    event_data = existing_event_docs[0].to_dict()
    guild = ctx.guild
    
    destination_channel = guild.get_channel(event_data['destination_voice_channel_id'])
    if not destination_channel:
        await ctx.send(f"| ERREUR | LE SALON DE DESTINATION N'A PAS ÉTÉ TROUVÉ.", ephemeral=True)
        return

    participants_count = 0
    for user_id in event_data.get('participants', []):
        member = guild.get_member(user_id)
        if member and member.voice and member.voice.channel:
            try:
                await member.move_to(destination_channel, reason=f"Déplacement pour la partie {event_name}")
                participants_count += 1
                await asyncio.sleep(0.5) # Pour éviter de dépasser la limite de requêtes de Discord
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour déplacer {member.display_name}.")
            except Exception as e:
                print(f"Erreur lors du déplacement de {member.display_name}: {e}")

    if participants_count > 0:
        await ctx.send(f"| INFO | {participants_count} JOUEURS ONT ÉTÉ DÉPLACÉS VERS {destination_channel.mention}", ephemeral=False)
    else:
        await ctx.send(f"| INFO | AUCUN JOUEUR À DÉPLACER POUR LA PARTIE '{event_name.upper()}'", ephemeral=True)


@bot.command(name='list_events')
async def list_events(ctx):
    """
    Affiche la liste de tous les événements actifs.
    """
    events_ref = db.collection('events')
    active_events_docs = events_ref.stream()

    events_list = []
    for doc in active_events_docs:
        events_list.append(doc.to_dict())

    if not events_list:
        await ctx.send("```\n[AUCUNE PARTIE EN COURS]\n```", ephemeral=True)
        return

    embed = discord.Embed(
        title="| PARTIES ACTIVES |",
        description="Voici la liste des parties en cours :",
        color=discord.Color.from_rgb(0, 158, 255) # Bleu électrique
    )

    for data in events_list:
        guild = bot.get_guild(data['guild_id'])
        role = guild.get_role(data['role_id']) if guild else None
        text_channel = guild.get_channel(data['text_channel_id']) if guild else None
        waiting_room_channel = guild.get_channel(data['waiting_room_channel_id']) if guild else None

        participants_count = len(data.get('participants', []))
        
        embed.add_field(
            name=f"🎮 {data['name'].upper()}",
            value=(
                f"**Rôle requis :** {role.mention if role else 'NON TROUVÉ'}\n"
                f"**Salon de jeu :** {text_channel.mention if text_channel else 'NON TROUVÉ'}\n"
                f"**Salon d'attente :** {waiting_room_channel.mention if waiting_room_channel else 'NON TROUVÉ'}\n"
                f"**Joueurs inscrits :** {participants_count} / {data['max_participants']} {data['participant_label']}\n"
                f"**Fin de partie :** <t:{int(data['end_time'].timestamp())}:R>"
            ),
            inline=False
        )
    embed.set_footer(text="| P.O.X.E.L | Base de données des parties", icon_url="https://images.emojiterra.com/google/noto-emoji/v2.034/512px/1f47d.png")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


@bot.command(name='intro', usage='[description]')
@commands.has_permissions(manage_guild=True)
async def intro_command(ctx):
    """
    Affiche la présentation de Poxel et ses commandes.
    """
    embed = discord.Embed(
        title="| P.O.X.E.L ASSISTANT |",
        description=(
            f"**Bonjour waeky !**\n"
            f"Je suis Poxel, votre assistant personnel pour l'organisation de parties de jeux.\n"
            f"Utilisez `!help poxel` pour voir toutes mes commandes."
        ),
        color=discord.Color.from_rgb(145, 70, 255) # Violet de Twitch
    )
    embed.set_footer(text="Système en ligne.", icon_url="https://images.emojiterra.com/google/noto-emoji/v2.034/512px/1f47d.png")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


async def handle_event_participation(interaction: discord.Interaction, event_firestore_id: str, action: str):
    """
    Gère les clics sur les boutons "START" et "EXIT".
    """
    user = interaction.user
    event_ref = db.collection('events').document(event_firestore_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        await interaction.response.send_message("| ALERTE | CETTE PARTIE N'EST PLUS ACTIVE", ephemeral=True)
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = interaction.guild
    role = guild.get_role(event_data['role_id'])

    if not role:
        await interaction.response.send_message("| ERREUR | RÔLE DE JOUEUR INTROUVABLE", ephemeral=True)
        return

    current_participants = set(event_data.get('participants', []))
    max_participants = event_data['max_participants']
    
    if action == 'join':
        if user.id in current_participants:
            await interaction.response.send_message("| ALERTE | VOUS ÊTES DÉJÀ DANS LA PARTIE", ephemeral=True)
            return
        if len(current_participants) >= max_participants:
            await interaction.response.send_message("| ALERTE | NOMBRE DE JOUEURS MAXIMAL ATTEINT", ephemeral=True)
            return

        try:
            # Ajoute le rôle directement et met à jour Firestore
            await user.add_roles(role, reason=f"Participation à la partie {event_name}")
            event_ref.update({'participants': firestore.ArrayUnion([user.id])})
            updated_event_data = event_ref.get().to_dict()
            
            await _update_event_embed(guild, updated_event_data, event_data['message_id'])
            await interaction.response.send_message(f"| INFO | BIENVENUE DANS LA PARTIE ! Votre rôle '{role.name}' a été activé. Dirigez-vous vers le salon vocal de la partie pour commencer.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("| ERREUR | PERMISSIONS INSUFFISANTES pour donner le rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"| ERREUR | INATTENDUE PENDANT L'INSCRIPTION : `{e}`", ephemeral=True)
            return

    elif action == 'leave':
        if user.id not in current_participants:
            await interaction.response.send_message("| ALERTE | VOUS NE PARTICIPEZ PAS À CETTE PARTIE", ephemeral=True)
            return

        try:
            # Retire le rôle et met à jour Firestore
            await user.remove_roles(role, reason=f"Quitte la partie {event_name}")
            event_ref.update({'participants': firestore.ArrayRemove([user.id])})
            updated_event_data = event_ref.get().to_dict()
            
            await _update_event_embed(guild, updated_event_data, event_data['message_id'])
            await interaction.response.send_message(f"| INFO | À LA PROCHAINE FOIS, {user.display_name.upper()}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("| ERREUR | PERMISSIONS INSUFFISANTES pour retirer le rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"| ERREUR | INATTENDUE PENDANT LE DÉSENGAGEMENT : `{e}`", ephemeral=True)
            return


@bot.event
async def on_interaction(interaction: discord.Interaction):
    """
    Écoute toutes les interactions, y compris les clics sur les boutons.
    """
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data['custom_id']
        if custom_id.startswith("join_event_"):
            event_firestore_id = custom_id.replace("join_event_", "")
            await handle_event_participation(interaction, event_firestore_id, 'join')
        elif custom_id.startswith("leave_event_"):
            event_firestore_id = custom_id.replace("leave_event_", "")
            await handle_event_participation(interaction, event_firestore_id, 'leave')
    
    # S'assure que les commandes sont toujours traitées
    await bot.process_commands(interaction)


@tasks.loop(minutes=1)
async def check_expired_events():
    """
    Tâche en arrière-plan pour vérifier et terminer les événements expirés.
    """
    print("Vérification des parties expirées...")
    events_ref = db.collection('events')
    now = datetime.now()
    for doc in events_ref.stream():
        event_data = doc.to_dict()
        event_end_time = event_data.get('end_time')
        
        if event_end_time and event_end_time < now:
            print(f"Partie '{event_data.get('name', doc.id)}' expirée. Fin de la partie...")
            await _end_event(doc.id)


@bot.command(name='help', usage='poxel')
async def help_command(ctx, bot_name: str = None):
    """
    Affiche toutes les commandes disponibles du bot Poxel.
    """
    if bot_name and bot_name.lower() != 'poxel':
        await ctx.send("| ERREUR | BOT INCONNU", ephemeral=True)
        return

    embed = discord.Embed(
        title="| MANUEL DU JOUEUR |",
        description="Voici la liste des commandes disponibles pour Poxel :",
        color=discord.Color.from_rgb(0, 158, 255) # Bleu électrique
    )

    commands_info = {
        "create_event": {
            "description": "Crée une nouvelle partie avec un rôle temporaire et deux salons vocaux.",
            "usage": ("`!create_event @rôle #salon_textuel durée(ex: 2h) max_participants étiquette_participants #salon_attente #salon_de_jeu Nom de la partie`\n"
                      "Ex: `!create_event @Joueur #salon-jeu 1h30m 4 joueurs #salle-d-attente #salon-partie Partie de Donjons`")
        },
        "end_event": {
            "description": "Termine une partie en cours et retire les rôles aux participants.",
            "usage": "`!end_event Nom de la partie`\n"
                     "Ex: `!end_event Partie de Donjons`"
        },
        "move_participants": {
            "description": "Déplace tous les participants d'une partie vers le salon de jeu.",
            "usage": "`!move_participants Nom de la partie`\n"
                     "Ex: `!move_participants Partie de Donjons`"
        },
        "list_events": {
            "description": "Affiche toutes les parties en cours avec leurs détails.",
            "usage": "`!list_events`"
        },
        "intro": {
            "description": "Affiche la présentation de Poxel sur le serveur.",
            "usage": "`!intro`"
        },
        "help": {
            "description": "Affiche ce manuel du joueur.",
            "usage": "`!help poxel`"
        }
    }

    for command_name, info in commands_info.items():
        embed.add_field(
            name=f"**!{command_name}**",
            value=(
                f"> **Info :** {info['description']}\n"
                f"> **Syntaxe :** {info['usage']}\n"
            ),
            inline=False
        )
    
    embed.set_footer(text="| P.O.X.E.L | Bon jeu, waeky !", icon_url="https://images.emojiterra.com/google/noto-emoji/v2.034/512px/1f47d.png")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


# ==============================================================================
# === LOGIQUE DE REPLIT KEEP-ALIVE ===
# Utilise un serveur Flask sur le thread principal pour rester actif, et
# exécute le bot Discord sur un thread séparé.
# ==============================================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Le Bot Discord Poxel est en ligne !"

def run_flask_app():
    """Exécute le serveur Flask sur un thread."""
    app.run(host='0.0.0.0', port=8080)

def run_bot():
    """Exécute le bot Discord."""
    bot.run(TOKEN)

# Démarre le bot sur un thread séparé
bot_thread = threading.Thread(target=run_bot)
bot_thread.daemon = True
bot_thread.start()

# Exécute l'application Flask sur le thread principal
# C'est ce qui maintient le projet Replit actif.
if __name__ == "__main__":
    run_flask_app()
