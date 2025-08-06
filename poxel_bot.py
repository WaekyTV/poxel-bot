import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
import re
import os

# Import des bibliothèques Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# --- Configuration du Bot ---
# On récupère le TOKEN depuis les variables d'environnement de Replit pour des raisons de sécurité.
# Pour le configurer, va dans l'onglet 'Secrets' de Replit et ajoute une clé 'DISCORD_TOKEN' avec ton token.
TOKEN = os.environ['DISCORD_TOKEN']

# --- Configuration Firebase ---
# Le fichier 'serviceAccountKey.json' doit être dans le même dossier que ce script.
try:
    # On initialise la connexion à Firebase en utilisant le fichier de clé.
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"Erreur lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assure-toi que 'serviceAccountKey.json' est présent et valide.")
    # Quitter si Firebase ne peut pas être initialisé, car le bot ne fonctionnera pas correctement.
    exit()


# Les "intents" sont les permissions que ton bot demande à Discord.
intents = discord.Intents.default()
intents.message_content = True # Nécessaire pour lire le contenu des messages (commandes)
intents.members = True         # Nécessaire pour gérer les rôles des membres
intents.guilds = True          # Nécessaire pour accéder aux informations du serveur

# Initialisation du bot avec un préfixe de commande (ex: !create_event)
# Désactiver l'aide par défaut de discord.py pour la remplacer par la nôtre
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- Fonctions Utilitaires ---

def parse_duration(duration_str: str) -> int:
    """
    Parse une chaîne de durée (ex: "2h", "30m", "5s") en secondes.
    Supporte les heures (h), minutes (m) et secondes (s).
    """
    total_seconds = 0
    # Regex pour trouver les nombres suivis de h, m, ou s
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

# --- Événements du Bot ---

@bot.event
async def on_ready():
    """
    Se déclenche lorsque le bot est connecté à Discord.
    """
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    print('Prêt à gérer les événements !')
    # Démarrer la tâche de vérification des événements expirés au démarrage du bot
    check_expired_events.start()

@bot.event
async def on_command_error(ctx, error):
    """
    Gère les erreurs de commande.
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Erreur de syntaxe : Il manque un argument pour cette commande. Utilisation correcte : `{ctx.command.usage}`", ephemeral=True)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Erreur d'argument : Argument invalide. Veuillez vérifier le format de vos arguments.", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Accès refusé : Vous n'avez pas les permissions nécessaires pour exécuter cette commande (Gérer les rôles).", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass # Ignorer les commandes non trouvées
    else:
        print(f"Erreur de commande : {error}")
        await ctx.send(f"Erreur du système : Une erreur inattendue s'est produite : `{error}`", ephemeral=True)

# --- Commandes du Bot ---

@bot.command(name='create_event', usage='<@rôle> <#salon> <durée (ex: 2h, 30m)> <max_participants> <étiquette_participants> <Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def create_event(ctx, role: discord.Role, channel: discord.TextChannel, duration_str: str, max_participants: int, participant_label: str, *event_name_parts):
    """
    Crée un nouvel événement avec un rôle temporaire, un salon, une durée et une capacité maximale.
    Ex: !create_event @RoleGaming #salon-prive-gaming 2h 10 joueurs Soirée Gaming Communauté
    """
    event_name = " ".join(event_name_parts)
    if not event_name:
        await ctx.send("Veuillez spécifier un nom pour l'événement.", ephemeral=True)
        return

    # Vérifier si l'événement existe déjà dans Firestore
    events_ref = db.collection('events')
    existing_event = events_ref.where('name', '==', event_name).get()
    if existing_event:
        await ctx.send(f"Un événement nommé '{event_name}' existe déjà.", ephemeral=True)
        return

    if max_participants <= 0:
        await ctx.send("Le nombre maximum de participants doit être supérieur à zéro.", ephemeral=True)
        return

    try:
        duration_seconds = parse_duration(duration_str)
    except ValueError as e:
        await ctx.send(str(e), ephemeral=True)
        return

    end_time = datetime.now() + timedelta(seconds=duration_seconds)

    # Créer un message temporaire pour obtenir l'ID du message avant de le mettre à jour
    temp_message = await ctx.send("Création de l'événement en cours...")

    # Sauvegarder l'événement dans Firestore
    event_data_firestore = {
        'name': event_name,
        'role_id': role.id,
        'channel_id': channel.id,
        'end_time': end_time, # Firestore gère les objets datetime nativement
        'max_participants': max_participants,
        'participant_label': participant_label,
        'participants': [], # Liste vide pour Firestore
        'message_id': temp_message.id, # L'ID du message Discord
        'guild_id': ctx.guild.id
    }
    doc_ref = db.collection('events').add(event_data_firestore)
    event_firestore_id = doc_ref[1].id # L'ID du document Firestore

    # Création des boutons avec des labels simples pour un aspect rétro
    view = discord.ui.View(timeout=None)
    
    join_button = discord.ui.Button(
        label="PARTICIPER", 
        style=discord.ButtonStyle.blurple, 
        custom_id=f"join_event_{event_firestore_id}"
    )
    leave_button = discord.ui.Button(
        label="QUITTER", 
        style=discord.ButtonStyle.red, 
        custom_id=f"leave_event_{event_firestore_id}"
    )
    
    view.add_item(join_button)
    view.add_item(leave_button)

    # Mettre à jour le message Discord avec les infos complètes et les boutons
    embed = discord.Embed(
        title=f"NEW EVENT: {event_name}",
        description=(
            f"**[ROLE]      :** {role.mention}\n"
            f"**[SALON]     :** {channel.mention}\n"
            f"**[DUREE]     :** {duration_str} (se termine <t:{int(end_time.timestamp())}:R>)\n"
            f"**[CAPACITE]  :** **0** / {max_participants} {participant_label}\n\n"
            "Cliquez sur les boutons pour rejoindre ou quitter la partie !"
        ),
        color=discord.Color.from_rgb(0, 158, 255) # Bleu 009EFF
    )
    embed.set_footer(text="[GESTION PAR POXEL] | MODE RETRO | WAEKY")
    embed.timestamp = datetime.now()

    await temp_message.edit(content=None, embed=embed, view=view)
    await ctx.send(f"L'événement **'{event_name}'** a été créé avec succès et se terminera dans {duration_str}.", ephemeral=True)


async def _end_event(event_doc_id: str):
    """
    Fonction interne pour terminer un événement, retirer les rôles et nettoyer.
    Prend l'ID du document Firestore.
    """
    event_ref = db.collection('events').document(event_doc_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        print(f"Tentative de terminer un événement non existant dans Firestore : {event_doc_id}")
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = bot.get_guild(event_data['guild_id'])
    
    if not guild:
        print(f"Guilde non trouvée pour l'événement {event_name} (ID: {event_doc_id})")
        event_ref.delete() # Supprimer de Firestore si la guilde n'existe plus
        return

    role = guild.get_role(event_data['role_id'])
    channel = guild.get_channel(event_data['channel_id'])

    # Retirer le rôle à tous les participants
    for user_id in list(event_data.get('participants', [])):
        member = guild.get_member(user_id)
        if member and role:
            try:
                await member.remove_roles(role, reason=f"Fin de l'événement {event_name}")
                print(f"Rôle {role.name} retiré à {member.display_name} pour l'événement {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")

    # Supprimer l'événement de Firestore
    event_ref.delete()
    print(f"Événement '{event_name}' (ID: {event_doc_id}) supprimé de Firestore.")

    # Envoyer un message de fin d'événement
    if channel:
        try:
            await channel.send(f"L'événement **'{event_name}'** est maintenant terminé. Le rôle {role.mention if role else 'temporaire'} a été retiré aux participants.")
        except discord.Forbidden:
            print(f"Permissions insuffisantes pour envoyer un message dans le salon {channel.name}")
    else:
        print(f"Salon de l'événement {event_name} non trouvé.")

    # Mettre à jour le message de l'événement pour indiquer qu'il est terminé
    try:
        event_message = await channel.fetch_message(event_data['message_id'])
        if event_message:
            embed = event_message.embeds[0]
            embed.color = discord.Color.from_rgb(150, 0, 0) # Couleur rouge foncé pour la fin
            embed.title = f"EVENT TERMINE: {event_name}"
            embed.description = f"**[FIN]**\n\n" \
                                f"**[ROLE]      :** {role.mention if role else 'Non specifie'}\n" \
                                f"**[SALON]     :** {channel.mention if channel else 'Non specifie'}\n" \
                                f"**[CAPACITE]  :** {len(event_data.get('participants', []))} / {event_data['max_participants']} {event_data['participant_label']}\n"
            embed.set_footer(text="[GESTION PAR POXEL] | EVENEMENT EXPIRE | WAEKY")
            await event_message.edit(embed=embed, view=None) # view=None pour retirer les boutons
    except discord.NotFound:
        print(f"Message de l'événement {event_name} (ID: {event_doc_id}) non trouvé sur Discord. Il a peut-être été supprimé manuellement.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message de l'événement : {e}")


@bot.command(name='end_event', usage='<Nom de l\'événement>')
@commands.has_permissions(manage_roles=True)
async def end_event_command(ctx, *event_name_parts):
    """
    Termine manuellement un événement et retire les rôles aux participants.
    Ex: !end_event Soirée Gaming Communauté
    """
    event_name = " ".join(event_name_parts)
    events_ref = db.collection('events')
    existing_event_docs = events_ref.where('name', '==', event_name).get()

    if not existing_event_docs:
        await ctx.send(f"L'événement **'{event_name}'** n'existe pas ou est déjà terminé.", ephemeral=True)
        return

    # Il devrait n'y avoir qu'un seul événement avec ce nom
    event_doc_id = existing_event_docs[0].id
    
    await ctx.send(f"L'événement **'{event_name}'** est en cours de fermeture...", ephemeral=True)
    await _end_event(event_doc_id)
    await ctx.send(f"L'événement **'{event_name}'** a été terminé manuellement.", ephemeral=True)


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
        await ctx.send("[STATUS] Aucun evenement actif pour le moment.", ephemeral=True)
        return

    embed = discord.Embed(
        title="[ LISTE DES EVENEMENTS EN COURS ]",
        description="```\nSTATUS : ACTIVATED\n```\nVoici la liste des evenements actifs sur le serveur :",
        color=discord.Color.from_rgb(145, 70, 255) # Violet Twitch
    )
    # embed.set_thumbnail(url="https://i.imgur.com/8QzQy3I.png") # Exemple d'icône 8bit pour un visuel rétro

    for data in events_list:
        guild = bot.get_guild(data['guild_id'])
        role = guild.get_role(data['role_id']) if guild else None
        channel = guild.get_channel(data['channel_id']) if guild else None
        
        participants_count = len(data.get('participants', []))
        
        embed.add_field(
            name=f"**{data['name']}**",
            value=(
                f"```\n"
                f"[ROLE]       : {role.name if role else 'INTROUVABLE'}\n"
                f"[SALON]      : {channel.name if channel else 'INTROUVABLE'}\n"
                f"[PARTICIPANTS] : {participants_count} / {data['max_participants']}\n"
                f"[FIN]        : <t:{int(data['end_time'].timestamp())}:R>\n"
                f"```"
            ),
            inline=False
        )
    embed.set_footer(text="[GESTION PAR POXEL] | PRET POUR LE COMBAT | WAEKY")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


async def handle_event_participation(interaction: discord.Interaction, event_firestore_id: str, action: str):
    """
    Gère les clics sur les boutons "Participer" et "Quitter".
    Prend l'ID du document Firestore.
    """
    user = interaction.user
    event_ref = db.collection('events').document(event_firestore_id)
    event_doc = event_ref.get()

    if not event_doc.exists:
        await interaction.response.send_message("Cet evenement n'existe plus ou a ete termine.", ephemeral=True)
        return

    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild = interaction.guild
    role = guild.get_role(event_data['role_id'])

    if not role:
        await interaction.response.send_message("Le role associe a cet evenement n'a pas ete trouve. L'evenement est peut-etre mal configure.", ephemeral=True)
        return

    current_participants = set(event_data.get('participants', []))
    max_participants = event_data['max_participants']
    participant_label = event_data['participant_label']

    if action == 'join':
        if user.id in current_participants:
            await interaction.response.send_message("Vous participez deja a cet evenement.", ephemeral=True)
            return
        if len(current_participants) >= max_participants:
            await interaction.response.send_message("Desole, cet evenement a atteint sa capacite maximale.", ephemeral=True)
            return

        try:
            await user.add_roles(role, reason=f"Participation a l'evenement {event_name}")
            current_participants.add(user.id)
            event_ref.update({'participants': firestore.ArrayUnion([user.id])})
            await interaction.response.send_message(f"Rejoindre reussi ! Vous avez rejoint l'evenement **'{event_name}'**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions necessaires pour vous donner ce role. Veuillez contacter un administrateur du serveur.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre inscription : `{e}`", ephemeral=True)
            return

    elif action == 'leave':
        if user.id not in current_participants:
            await interaction.response.send_message("Vous ne participez pas a cet evenement.", ephemeral=True)
            return

        try:
            await user.remove_roles(role, reason=f"Quitte l'evenement {event_name}")
            current_participants.remove(user.id)
            event_ref.update({'participants': firestore.ArrayRemove([user.id])})
            await interaction.response.send_message(f"Desinscription reussie ! Vous avez quitte l'evenement **'{event_name}'**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions necessaires pour vous retirer ce role. Veuillez contacter un administrateur du serveur.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre desinscription : `{e}`", ephemeral=True)
            return

    updated_event_doc = event_ref.get()
    if updated_event_doc.exists:
        updated_event_data = updated_event_doc.to_dict()
        updated_participants_count = len(updated_event_data.get('participants', []))
        
        try:
            original_message = interaction.message
            if original_message:
                embed = original_message.embeds[0]
                description_lines = embed.description.split('\n')
                for i, line in enumerate(description_lines):
                    if "[CAPACITE]" in line:
                        description_lines[i] = f"**[CAPACITE]  :** **{updated_participants_count}** / {max_participants} {participant_label}"
                        break
                embed.description = '\n'.join(description_lines)
                await original_message.edit(embed=embed)
        except Exception as e:
            print(f"Erreur lors de la mise à jour du message de l'événement : {e}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """
    Écoute toutes les interactions (y compris les clics sur les boutons).
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


@tasks.loop(minutes=1) # Vérifie les événements toutes les minutes
async def check_expired_events():
    """
    Tâche en arrière-plan pour vérifier et terminer les événements expirés.
    """
    print("Vérification des événements expirés...")
    events_ref = db.collection('events')
    now = datetime.now()
    for doc in events_ref.stream():
        event_data = doc.to_dict()
        event_end_time = event_data.get('end_time')
        
        if event_end_time and event_end_time < now:
            print(f"Événement '{event_data.get('name', doc.id)}' expiré. Fin de l'événement...")
            await _end_event(doc.id)


@bot.command(name='help', usage='poxel')
async def help_command(ctx, bot_name: str = None):
    """
    Affiche toutes les commandes disponibles du bot Poxel.
    Utilisation: !help poxel
    """
    if bot_name and bot_name.lower() != 'poxel':
        await ctx.send("Désolé, je ne suis pas ce bot. Pour l'aide de Poxel, utilisez `!help poxel`.", ephemeral=True)
        return

    embed = discord.Embed(
        title="[POXEL | ASSISTANT VIRTUALISE]",
        description="```\nSYSTEME EN LIGNE\n```\nJe suis Poxel, votre assistant pour gerer les evenements sur Discord. Voici les commandes :",
        color=discord.Color.from_rgb(145, 70, 255) # Violet Twitch
    )

    commands_info = {
        "create_event": {
            "description": "Cree un nouvel evenement.",
            "usage": "`!create_event @role #salon duree(ex: 2h) max_participants etiquette Nom de l'evenement`\n"
                     "Ex: `!create_event @Joueur #salon-jeu 1h30m 4 joueurs Partie de Donjons`\n"
                     "*(Cette commande a plusieurs parametres.)*"
        },
        "end_event": {
            "description": "Termine un evenement en cours.",
            "usage": "`!end_event Nom de l'evenement`\n"
                     "Ex: `!end_event Ma Super Partie`"
        },
        "list_events": {
            "description": "Affiche tous les evenements actifs.",
            "usage": "`!list_events`"
        },
        "help": {
            "description": "Affiche ce message d'aide.",
            "usage": "`!help poxel`"
        }
    }

    for command_name, info in commands_info.items():
        embed.add_field(
            name=f"**[ COMMANDE : {command_name.upper()} ]**",
            value=f"```\n{info['description']}\n```\nUtilisation : {info['usage']}",
            inline=False
        )
    
    embed.set_footer(text="[POXEL.EXE] | PRET POUR LE COMBAT | WAEKY")
    embed.timestamp = datetime.now()
    await ctx.send(embed=embed)


# --- Démarrage du Bot ---
# Assure-toi que ton TOKEN est bien configuré avant de lancer le bot.
bot.run(TOKEN)
