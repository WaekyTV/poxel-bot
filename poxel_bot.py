import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio
import re  # Pour parser la durée
import os  # Pour accéder aux variables d'environnement (le TOKEN)
import json # Pour parser le JSON des identifiants Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# ==============================================================================
# === INSTRUCTIONS IMPORTANTES POUR L'HÉBERGEMENT HORS REPLIT ===
# ==============================================================================
# Ce code est optimisé pour fonctionner sur une plateforme d'hébergement
# qui maintient les processus actifs en continu (comme Render, Heroku, etc.).
#
# 1. DÉPENDANCES : Assurez-vous que les bibliothèques suivantes sont installées
#    dans l'environnement de déploiement :
#    - discord.py
#    - firebase-admin
#    Un fichier `requirements.txt` est recommandé pour cela.
#
# 2. VARIABLES D'ENVIRONNEMENT : Le TOKEN Discord et les identifiants Firebase
#    doivent être configurés comme des variables d'environnement sur votre
#    service d'hébergement.
#    - DISCORD_TOKEN : Votre jeton Discord.
#    - FIREBASE_CREDENTIALS_JSON : Le contenu complet du fichier
#      'serviceAccountKey.json' sous forme de chaîne de caractères JSON.
# ==============================================================================

# --- Configuration du Bot ---
# Récupère le TOKEN depuis les variables d'environnement.
TOKEN = os.environ.get('DISCORD_TOKEN')

if not TOKEN:
    print("ERREUR : Le TOKEN Discord n'est pas configuré dans les variables d'environnement.")
    exit()

# --- Configuration Firebase ---
try:
    # Récupère les identifiants depuis la variable d'environnement
    firebase_credentials_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if not firebase_credentials_json:
        print("ERREUR : La variable d'environnement 'FIREBASE_CREDENTIALS_JSON' est manquante.")
        exit()

    cred_dict = json.loads(firebase_credentials_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"ERREUR lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assurez-vous que 'FIREBASE_CREDENTIALS_JSON' est valide.")
    exit()

# Les "intents" sont les permissions que le bot demande à Discord.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

# Initialisation du bot avec un préfixe de commande '!' et les intents spécifiés.
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
        
        participants_field_value = "\n".join(participants_mentions) if participants_mentions else "*Aucun participant inscrit pour le moment.*"

        embed.set_field_at(
            0,
            name=f"**Participants ({len(participants_mentions)} / {event_data['max_participants']})**",
            value=participants_field_value,
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
        pass
    else:
        print(f"Erreur de commande : {error}")
        await ctx.send(f"| ERREUR | INATTENDUE : `{error}`", ephemeral=True)

# --- Commandes du Bot ---

@bot.command(name='create_event', usage="<@rôle> <durée (ex: 2h, 30m)> <max_participants> <étiquette_participants> <#salon_rendez-vous_vocal> <#salle_de_l'event_vocal> <Nom de la partie>")
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, duration_str: str, max_participants: int, participant_label: str, waiting_room_channel: discord.VoiceChannel, destination_voice_channel: discord.VoiceChannel, *event_name_parts):
    """
    Crée une nouvelle partie avec un rôle temporaire, un salon de rendez-vous et une durée.

    Exemple d'utilisation :
    `!create_event @Joueur 1h30m 4 joueurs #point-de-ralliement #salle-de-l'event Partie de Donjons`
    """
    event_name = " ".join(event_name_parts)
    if not event_name:
        await ctx.send("| ERREUR | NOM DE LA PARTIE MANQUANT", ephemeral=True)
        return

    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()
    
    if existing_event_docs:
        existing_event_doc = existing_event_docs[0]
        event_data = existing_event_doc.to_dict()
        
        # Vérifie si l'événement existant est expiré
        if datetime.now(timezone.utc) > event_data['end_time'].replace(tzinfo=timezone.utc):
            await ctx.send(f"| INFO | L'ancien événement '{event_name}' est expiré. Clôture automatique en cours pour en créer un nouveau...", ephemeral=True)
            await _end_event(existing_event_doc.id)
        else:
            await ctx.send(f"| ERREUR | LA PARTIE '{event_name}' EXISTE DÉJÀ ET N'EST PAS TERMINÉE", ephemeral=True)
            return

    if max_participants <= 0:
        await ctx.send("| ERREUR | CAPACITÉ DE PARTICIPANTS INVALIDE", ephemeral=True)
        return

    try:
        duration_seconds = parse_duration(duration_str)
    except ValueError as e:
        await ctx.send(f"| ERREUR | {str(e).upper()}", ephemeral=True)
        return

    end_time = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
    temp_message = await ctx.send(">>> Chargement de la partie...")

    event_data_firestore = {
        'name': event_name,
        'role_id': role.id,
        'text_channel_id': ctx.channel.id, # Utilise le salon où la commande a été lancée
        'waiting_room_channel_id': waiting_room_channel.id,
        'destination_voice_channel_id': destination_voice_channel.id,
        'end_time': end_time,
        'max_participants': max_participants,
        'participant_label': participant_label,
        'participants': [],
        'message_id': temp_message.id,
        'guild_id': ctx.guild.id
    }
    doc_ref = db.collection('events').add(event_data_firestore)
    event_firestore_id = doc_ref[1].id

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

    embed = discord.Embed(
        title=f"NOUVELLE PARTIE : {event_name.upper()}",
        description=f"**Une nouvelle partie a été lancée ! Préparez-vous à jouer !**\n\n"
                    f"Le rôle `{role.name}` vous sera attribué. Une fois inscrit, veuillez rejoindre le **point de ralliement** et patienter d'être déplacé.",
        color=discord.Color.from_rgb(255, 0, 154)
    )
    embed.add_field(name=f"**Participants ({max_participants})**", value="*Aucun participant inscrit pour le moment.*", inline=False)
    embed.add_field(name="**Rôle attribué :**", value=f"{role.mention}", inline=True)
    embed.add_field(name="**Point de ralliement :**", value=f"{waiting_room_channel.mention}", inline=True)
    embed.add_field(name="**Durée :**", value=f"{duration_str} (Fin de partie <t:{int(end_time.timestamp())}:R>)", inline=False)
    embed.set_footer(text="| POXEL | Appuyez sur START pour participer.")
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

    # Envoie le message de fin de partie avant de supprimer l'événement
    if text_channel:
        try:
            await text_channel.send(f"| ALERTE | L'événement **'{event_name.upper()}'** est maintenant clos.")
        except discord.Forbidden:
            print(f"Permissions insuffisantes pour envoyer un message dans le salon {text_channel.name}")
    else:
        print(f"Salon de la partie {event_name} non trouvé.")

    try:
        event_message = await text_channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = event_message.embeds[0]
            embed.color = discord.Color.from_rgb(0, 158, 255)
            embed.title = f"PARTIE TERMINÉE : {event_name.upper()}"
            embed.description = f"**La partie est terminée. Bien joué !**"
            embed.clear_fields()
            embed.add_field(name="**Participants finaux :**", value=f"{len(event_data.get('participants', []))} / {event_data['max_participants']} {event_data['participant_label']}", inline=False)
            await event_message.edit(embed=embed, view=None)
    except discord.NotFound:
        print(f"Message de la partie {event_name} (ID: {event_doc_id}) non trouvé sur Discord. Il a peut-être été supprimé manuellement.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de la partie : {e}")

    # Supprime l'événement de Firestore une fois le nettoyage terminé
    event_ref.delete()
    print(f"Partie '{event_name}' (ID: {event_doc_id}) supprimée de Firestore.")


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
    Déplace tous les participants d'une partie vers la salle de l'événement.
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
                await asyncio.sleep(0.5)
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour déplacer {member.display_name}.")
            except Exception as e:
                print(f"Erreur lors du déplacement de {member.display_name}: {e}")

    if participants_count > 0:
        await ctx.send(f"| INFO | {participants_count} PARTICIPANTS ONT ÉTÉ DÉPLACÉS", ephemeral=False)
    else:
        await ctx.send(f"| INFO | AUCUN PARTICIPANT À DÉPLACER POUR LA PARTIE '{event_name.upper()}'", ephemeral=True)


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
        color=discord.Color.from_rgb(0, 158, 255)
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
                f"**Rôle attribué :** {role.mention if role else 'NON TROUVÉ'}\n"
                f"**Point de ralliement :** {waiting_room_channel.mention if waiting_room_channel else 'NON TROUVÉ'}\n"
                f"**Participants :** {participants_count} / {data['max_participants']} {data['participant_label']}\n"
                f"**Fin de partie :** <t:{int(data['end_time'].timestamp())}:R>"
            ),
            inline=False
        )
    embed.set_footer(text="| POXEL | Base de données des parties")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


@bot.command(name='intro', usage='[description]')
@commands.has_permissions(manage_guild=True)
async def intro_command(ctx):
    """
    Affiche la présentation de Poxel et ses commandes.
    """
    embed = discord.Embed(
        title="| POXEL ASSISTANT |",
        description=(
            f"**Bonjour waeky !**\n"
            f"Je suis POXEL, votre assistant personnel pour l'organisation de parties de jeux.\n"
            f"Utilisez `!help poxel` pour voir toutes mes commandes."
        ),
        color=discord.Color.from_rgb(145, 70, 255)
    )
    embed.set_footer(text="Système en ligne.")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


async def handle_event_participation(interaction: discord.Interaction, event_firestore_id: str, action: str):
    """
    Gère les clics sur les boutons "START" et "EXIT".
    """
    # Defer l'interaction pour avoir plus de temps pour répondre
    await interaction.response.defer(ephemeral=True)

    user = interaction.user
    event_ref = db.collection('events').document(event_firestore_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        await interaction.followup.send("| ALERTE | CETTE PARTIE N'EST PLUS ACTIVE", ephemeral=True)
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = interaction.guild
    role = guild.get_role(event_data['role_id'])
    
    # Vérifie si l'événement est déjà terminé
    if datetime.now(timezone.utc) > event_data['end_time'].replace(tzinfo=timezone.utc):
        await interaction.followup.send("| ALERTE | LA DURÉE DE LA PARTIE EST EXPIRÉE. L'événement est clos.", ephemeral=True)
        await _end_event(event_firestore_id)
        return

    if not role:
        await interaction.followup.send("| ERREUR | RÔLE DE PARTICIPANT INTROUVABLE", ephemeral=True)
        return

    current_participants = set(event_data.get('participants', []))
    max_participants = event_data['max_participants']
    
    if action == 'join':
        if user.id in current_participants:
            await interaction.followup.send("| ALERTE | VOUS ÊTES DÉJÀ INSCRIT À LA PARTIE", ephemeral=True)
            return
        if len(current_participants) >= max_participants:
            await interaction.followup.send("| ALERTE | NOMBRE DE PARTICIPANTS MAXIMAL ATTEINT", ephemeral=True)
            return

        try:
            await user.add_roles(role, reason=f"Participation à la partie {event_name}")
            event_ref.update({'participants': firestore.ArrayUnion([user.id])})
            updated_event_data = event_ref.get().to_dict()
            
            await _update_event_embed(guild, updated_event_data, event_data['message_id'])
            await interaction.followup.send(f"| INFO | BIENVENUE ! Vous avez reçu le rôle `{role.name}`. Veuillez vous rendre dans le **point de ralliement** et patienter d'être déplacé.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("| ERREUR | PERMISSIONS INSUFFISANTES pour donner le rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"| ERREUR | INATTENDUE PENDANT L'INSCRIPTION : `{e}`", ephemeral=True)
            return

    elif action == 'leave':
        if user.id not in current_participants:
            await interaction.followup.send("| ALERTE | VOUS NE PARTICIPEZ PAS À CETTE PARTIE", ephemeral=True)
            return

        try:
            await user.remove_roles(role, reason=f"Quitte la partie {event_name}")
            event_ref.update({'participants': firestore.ArrayRemove([user.id])})
            updated_event_data = event_ref.get().to_dict()
            
            await _update_event_embed(guild, updated_event_data, event_data['message_id'])
            await interaction.followup.send(f"| INFO | À LA PROCHAINE FOIS, {user.display_name.upper()}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("| ERREUR | PERMISSIONS INSUFFISANTES pour retirer le rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"| ERREUR | INATTENDUE PENDANT LE DÉSENGAGEMENT : `{e}`", ephemeral=True)
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
    
    await bot.process_commands(interaction)


@tasks.loop(minutes=1)
async def check_expired_events():
    """
    Tâche en arrière-plan pour vérifier et terminer les événements expirés.
    """
    print("Vérification des parties expirées...")
    events_ref = db.collection('events')
    now = datetime.now(timezone.utc)
    for doc in events_ref.stream():
        event_data = doc.to_dict()
        event_end_time = event_data.get('end_time')
        
        # S'assure que la date de fin est bien de type datetime et est en UTC pour la comparaison
        if isinstance(event_end_time, datetime) and event_end_time.replace(tzinfo=timezone.utc) < now:
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
        description="Voici la liste des commandes disponibles pour POXEL :",
        color=discord.Color.from_rgb(0, 158, 255)
    )

    commands_info = {
        "create_event": {
            "description": "Crée une nouvelle partie avec un rôle temporaire, un salon de rendez-vous et une durée.",
            "usage": ("`!create_event @rôle durée(ex: 2h) max_participants étiquette_participants #point_de_ralliement_vocal Nom de la partie`\n"
                      "Ex: `!create_event @Joueur 1h30m 4 joueurs joueurs #point-de-ralliement Partie de Donjons`")
        },
        "end_event": {
            "description": "Termine une partie en cours et retire les rôles aux participants.",
            "usage": "`!end_event Nom de la partie`\n"
                     "Ex: `!end_event Partie de Donjons`"
        },
        "move_participants": {
            "description": "Déplace tous les participants d'une partie vers la salle de l'événement.",
            "usage": "`!move_participants Nom de la partie`\n"
                     "Ex: `!move_participants Partie de Donjons`"
        },
        "list_events": {
            "description": "Affiche toutes les parties en cours avec leurs détails.",
            "usage": "`!list_events`"
        },
        "intro": {
            "description": "Affiche la présentation de POXEL sur le serveur.",
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
    
    embed.set_footer(text="| POXEL | Bon jeu, waeky !")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


# ==============================================================================
# === DÉMARRAGE DU BOT ===
# Exécute le bot Discord directement avec son TOKEN.
# Le reste de la logique (serveur web, threading) est géré par la plateforme
# d'hébergement.
# ==============================================================================
if __name__ == "__main__":
    bot.run(TOKEN)
