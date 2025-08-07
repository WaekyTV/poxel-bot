# -*- coding: utf-8 -*-
# --- INSTRUCTIONS POUR RENDER ---
# IMPORTANT : Ce code a été modifié pour fonctionner en tant que "Web Service"
# sur Render. Un serveur web minimal est démarré en parallèle du bot Discord
# pour écouter sur un port et éviter l'erreur de "timeout".
# Assurez-vous que les bibliothèques 'flask', 'pytz', 'discord.py' et 'firebase_admin'
# sont bien dans votre fichier 'requirements.txt'.


import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from datetime import datetime, timedelta
import asyncio
import os
import random
import re
import json
from dotenv import load_dotenv
import pytz # Import de la bibliothèque pour la gestion des fuseaux horaires
from typing import Optional
import threading # Pour démarrer le bot dans un thread séparé
from flask import Flask # Pour créer le serveur web minimal
from firebase_admin.firestore import firestore


# Import des bibliothèques Firebase
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Charger les variables d'environnement depuis le fichier .env (pour les tests locaux)
load_dotenv()


# Récupérer le token du bot depuis les variables d'environnement
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')


# --- Configuration Firebase ---
try:
    firebase_json_key = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY_JSON')
    if not firebase_json_key:
        raise ValueError("La variable d'environnement 'FIREBASE_SERVICE_ACCOUNT_KEY_JSON' n'est pas définie sur Render.")
    
    service_account_info = json.loads(firebase_json_key)
    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialisé avec succès.")
except Exception as e:
    print(f"Erreur lors de l'initialisation de Firebase Admin SDK: {e}")
    print("Assure-toi que la variable d'environnement 'FIREBASE_SERVICE_ACCOUNT_KEY_JSON' est bien configurée sur Render.")
    exit()


# Définir le préfixe de commande et les intents nécessaires
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True
intents.presences = True


# Initialiser le bot
bot = commands.Bot(command_prefix='!', intents=intents)


# --- Fonctions Utilitaires ---


# Définir le fuseau horaire de Paris
PARIS_TIMEZONE = pytz.timezone('Europe/Paris')


def parse_duration(duration_str: str) -> int:
    """
    Parse une chaîne de durée (ex: "2h", "30m") en secondes.
    """
    total_seconds = 0
    matches = re.findall(r'(\d+)([hms])', duration_str.lower())


    if not matches:
        raise ValueError("Format de durée invalide. Utilisez '2h', '30m' ou une combinaison.")


    for value, unit in matches:
        value = int(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
    return total_seconds


NEON_BLUE = 0x009EFF
NEON_RED = 0xFF073A
NEON_GREEN = 0x39FF14
PURPLE_START_COLOR = 0x6441a5 # Code hex pour la couleur demandée, noté pour référence mais non directement utilisable.


def create_retro_embed(title, description="", color=NEON_BLUE):
    """Crée un embed avec un style simple."""
    embed = discord.Embed(
        title=f"{title.upper()}",
        description=description,
        color=color
    )
    embed.set_author(name="Poxel OS", icon_url="https://placehold.co/64x64/009eff/ffffff?text=P")
    embed.set_footer(text="Système d'événements Poxel")
    return embed


async def get_participant_info(guild: discord.Guild, participants_data: list) -> str:
    """
    Récupère les pseudos Discord et les pseudos en jeu des participants.
    """
    participant_list = []
    for p_data in participants_data:
        member = guild.get_member(p_data['user_id'])
        if member:
            alias = p_data.get('alias', '')
            participant_list.append(f"**{member.display_name}** ({alias})" if alias else f"**{member.display_name}**")
    if not participant_list:
        return "Aucun participant"
    return "\n".join(participant_list)




# --- Classes de vues et de boutons pour l'interaction utilisateur ---


# Modèle pour le formulaire d'inscription
class AliasModal(discord.ui.Modal, title='Inscription à l\'événement'):
    def __init__(self, event_firestore_id: str):
        super().__init__()
        self.event_firestore_id = event_firestore_id


    alias_input = discord.ui.TextInput(
        label="Votre pseudo en jeu (optionnel)",
        style=discord.TextStyle.short,
        placeholder="Ex: PoxelBot2025",
        required=False,
        max_length=50
    )


    async def on_submit(self, interaction: discord.Interaction):
        """
        Gère la soumission du formulaire d'inscription.
        """
        await interaction.response.defer(ephemeral=True)
        alias = self.alias_input.value
        user = interaction.user
        event_ref = db.collection('events').document(self.event_firestore_id)
        
        event_doc = await asyncio.to_thread(event_ref.get)
        
        if not event_doc.exists:
            await interaction.followup.send("Cet événement n'existe plus ou a été terminé.", ephemeral=True)
            return


        event_data = event_doc.to_dict()
        event_name = event_data.get('name', 'Nom inconnu')
        guild = interaction.guild
        role_id = event_data.get('role_id')
        role = guild.get_role(role_id) if role_id else None


        if not role:
            await interaction.followup.send("Le rôle associé à cet événement n'a pas été trouvé.", ephemeral=True)
            return


        participants_list = event_data.get('participants', [])
        max_participants = event_data.get('max_participants')
        
        # Vérifier si l'utilisateur est déjà inscrit
        is_already_in = any(p['user_id'] == user.id for p in participants_list)
        if is_already_in:
            await interaction.followup.send("Vous êtes déjà inscrit à cet événement.", ephemeral=True)
            return


        # Vérifier si l'événement est plein ou a déjà commencé
        now = datetime.now(PARIS_TIMEZONE)
        start_time = event_data.get('start_time')
        
        if (max_participants and len(participants_list) >= max_participants) or \
           (start_time and start_time.astimezone(PARIS_TIMEZONE) <= now):
            await interaction.followup.send("Désolé, les inscriptions sont fermées.", ephemeral=True)
            return
        
        # Ajouter l'utilisateur
        try:
            await user.add_roles(role, reason=f"Participation à l'événement {event_name}")
            
            new_participant_data = {'user_id': user.id, 'alias': alias}
            await asyncio.to_thread(event_ref.update, {'participants': firestore.ArrayUnion([new_participant_data])})
            
            await interaction.followup.send(f"Vous avez rejoint l'événement **'{event_name}'** !", ephemeral=True)
            
            # Annoncer la nouvelle inscription
            channel_waiting_id = event_data.get('channel_waiting_id')
            if channel_waiting_id:
                channel_waiting = guild.get_channel(channel_waiting_id)
                if channel_waiting:
                    pseudo_msg = f"({alias})" if alias else ""
                    await channel_waiting.send(f"Bienvenue dans la partie **{user.display_name}** {pseudo_msg} !")
            
        except discord.Forbidden:
            await interaction.followup.send("Je n'ai pas les permissions nécessaires pour vous donner ce rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue lors de votre inscription : `{e}`", ephemeral=True)
            return
        
        # Mettre à jour l'embed après l'interaction
        updated_event_doc = await asyncio.to_thread(event_ref.get)
        if updated_event_doc.exists:
            await self.update_event_message(interaction, updated_event_doc.to_dict())


    async def update_event_message(self, interaction: discord.Interaction, event_data: dict):
        """Mise à jour de l'embed principal de l'événement et de ses boutons."""
        guild = interaction.guild
        participants = event_data.get('participants', [])
        max_participants = event_data.get('max_participants')
        participant_label = event_data.get('participant_label', 'participants')
        
        try:
            original_message = interaction.message
            if original_message:
                embed = original_message.embeds[0]
                
                # Mettre à jour le champ des participants
                participant_names = await get_participant_info(guild, participants)
                
                # Chercher le champ "Participants" par son nom
                participants_field_index = -1
                for i, field in enumerate(embed.fields):
                    if "Participants" in field.name:
                        participants_field_index = i
                        break


                if participants_field_index != -1:
                    embed.set_field_at(
                        index=participants_field_index,
                        name=f"Participants ({len(participants)}/{max_participants} {participant_label})",
                        value=participant_names,
                        inline=False
                    )
                
                # Vérifier si les inscriptions sont complètes et envoyer un message
                is_full = max_participants and len(participants) >= max_participants
                if is_full and not event_data.get('registrations_closed'):
                    channel_waiting = guild.get_channel(event_data.get('channel_waiting_id'))
                    if channel_waiting:
                        await channel_waiting.send(f"@everyone Les inscriptions pour l'événement **'{event_data.get('name', 'Nom inconnu')}'** sont complètes !")
                        await asyncio.to_thread(db.collection('events').document(self.event_firestore_id).update, {'registrations_closed': True})
                elif not is_full and event_data.get('registrations_closed'):
                    # Si l'événement n'est plus plein mais était marqué comme fermé
                    await asyncio.to_thread(db.collection('events').document(self.event_firestore_id).update, {'registrations_closed': False})


                # Gérer l'état du bouton en fonction du nombre de participants
                view = EventButtons(self.event_firestore_id, is_full=is_full)
                await original_message.edit(embed=embed, view=view)
        except discord.NotFound:
            print(f"Erreur : Le message original de l'événement {event_data.get('name', 'nom inconnu')} n'a pas été trouvé. Il a peut-être été supprimé.")
        except Exception as e:
            print(f"Erreur lors de la mise à jour du message de l'événement : {e}")




class EventButtons(View):
    def __init__(self, event_firestore_id: str, is_full: bool = False):
        super().__init__(timeout=None)
        self.event_firestore_id = event_firestore_id
        
        # Le bouton d'inscription change de style et de libellé si l'événement est complet
        join_button_style = discord.ButtonStyle.gray if is_full else discord.ButtonStyle.primary
        join_button_label = "Inscriptions fermées" if is_full else "START"


        join_button = Button(
            label=join_button_label, 
            style=join_button_style, 
            custom_id=f"join_event_{self.event_firestore_id}",
            disabled=is_full
        )
        join_button.callback = self.handle_join
        self.add_item(join_button)


        quit_button = Button(
            label="QUIT", 
            style=discord.ButtonStyle.red, 
            custom_id=f"quit_event_{self.event_firestore_id}"
        )
        quit_button.callback = self.handle_quit
        self.add_item(quit_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Vérifie l'état du bouton d'inscription avant de l'autoriser.
        Permet de désactiver le bouton de manière dynamique.
        """
        event_ref = db.collection('events').document(self.event_firestore_id)
        event_doc = await asyncio.to_thread(event_ref.get)
        
        if not event_doc.exists:
            await interaction.response.send_message("Cet événement n'existe plus ou a été terminé.", ephemeral=True)
            return False
            
        event_data = event_doc.to_dict()
        participants_list = event_data.get('participants', [])
        max_participants = event_data.get('max_participants')
        
        # Si le bouton "START" est cliqué et que les inscriptions sont fermées.
        if interaction.custom_id.startswith("join_event_"):
            if event_data.get('registrations_closed') or (max_participants and len(participants_list) >= max_participants):
                await interaction.response.send_message("Désolé, les inscriptions sont fermées.", ephemeral=True)
                return False
        
        return True


    async def handle_join(self, interaction: discord.Interaction):
        """Ouvre le modal pour l'inscription."""
        await interaction.response.send_modal(AliasModal(self.event_firestore_id))


    async def handle_quit(self, interaction: discord.Interaction):
        """Gère le clic sur le bouton 'QUIT'."""
        user = interaction.user
        event_ref = db.collection('events').document(self.event_firestore_id)
        event_doc = await asyncio.to_thread(event_ref.get)
        
        if not event_doc.exists:
            await interaction.response.send_message("Cet événement n'existe plus ou a été terminé.", ephemeral=True)
            return


        event_data = event_doc.to_dict()
        event_name = event_data.get('name', 'Nom inconnu')
        guild = interaction.guild
        role_id = event_data.get('role_id')
        role = guild.get_role(role_id) if role_id else None


        participants_list = event_data.get('participants', [])
        
        is_in_event = any(p['user_id'] == user.id for p in participants_list)
        if not is_in_event:
            await interaction.response.send_message("Vous ne participez pas à cet événement.", ephemeral=True)
            return


        try:
            # Récupérer l'entrée du participant à supprimer
            participant_to_remove = next((p for p in participants_list if p['user_id'] == user.id), None)
            
            if role:
                await user.remove_roles(role, reason=f"Quitte l'événement {event_name}")
            
            # Supprimer l'entrée du participant
            await asyncio.to_thread(event_ref.update, {'participants': firestore.ArrayRemove([participant_to_remove])})
            
            await interaction.response.send_message(f"Vous avez quitté l'événement **'{event_name}'**.", ephemeral=True)
            
            # --- Correction ajoutée : Gestion de la réouverture des inscriptions ---
            updated_event_doc = await asyncio.to_thread(event_ref.get)
            if updated_event_doc.exists:
                updated_data = updated_event_doc.to_dict()
                max_participants = updated_data.get('max_participants')
                current_participants_count = len(updated_data.get('participants', []))
                channel_waiting_id = updated_data.get('channel_waiting_id')


                # Si l'événement était plein et qu'une place se libère
                if updated_data.get('registrations_closed') and max_participants is not None and current_participants_count < max_participants:
                    await asyncio.to_thread(event_ref.update, {'registrations_closed': False})
                    if channel_waiting_id:
                        channel_waiting = guild.get_channel(channel_waiting_id)
                        if channel_waiting:
                            await channel_waiting.send(f"@everyone Une place s'est libérée pour l'événement **'{event_name}'** ! Inscriptions réouvertes !")
            
                # Mettre à jour l'embed après le désistement
                await AliasModal(self.event_firestore_id).update_event_message(interaction, updated_data)




        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour vous retirer ce rôle.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue lors de votre désinscription : `{e}`", ephemeral=True)
            return
        


# --- Tâche de gestion des événements ---


async def _end_event(event_doc_id: str, context_channel: Optional[discord.TextChannel] = None):
    """
    Fonction interne pour terminer un événement, retirer les rôles et nettoyer.
    """
    event_ref = db.collection('events').document(event_doc_id)
    event_doc = await asyncio.to_thread(event_ref.get)


    if not event_doc.exists:
        print(f"Tentative de terminer un événement non existant dans Firestore : {event_doc_id}")
        return


    event_data = event_doc.to_dict()
    event_name = event_data.get('name', 'Nom inconnu')
    guild_id = event_data.get('guild_id')
    guild = bot.get_guild(guild_id) if guild_id else None
    
    if not guild:
        print(f"Guilde non trouvée pour l'événement {event_name} (ID: {event_doc_id}). Suppression de l'événement.")
        await asyncio.to_thread(event_ref.delete)
        return


    role_id = event_data.get('role_id')
    role = guild.get_role(role_id) if role_id else None
    channel_waiting_id = event_data.get('channel_waiting_id')
    channel_waiting = guild.get_channel(channel_waiting_id) if channel_waiting_id else None
    
    participants_list = event_data.get('participants', [])


    # Retirer les rôles des participants
    for p_data in participants_list:
        member = guild.get_member(p_data['user_id'])
        if member and role:
            try:
                await member.remove_roles(role, reason=f"Fin de l'événement {event_name}")
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour retirer le rôle {role.name} à {member.display_name}")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle à {member.display_name}: {e}")
    
    # Mettre à jour le message de l'événement s'il existe
    event_message = None
    try:
        message_id = event_data.get('message_id')
        if channel_waiting and message_id:
            event_message = await channel_waiting.fetch_message(message_id)
    except discord.NotFound:
        print(f"Erreur : Message de l'événement {event_name} non trouvé. Il a peut-être été supprimé.")
    except Exception as e:
        print(f"Erreur lors de la récupération du message de l'événement : {e}")


    if event_message:
        try:
            embed = create_retro_embed(f"ÉVÉNEMENT CLÔTURÉ : {event_name}", color=NEON_RED)
            embed.description = "L'événement est maintenant terminé et les inscriptions sont fermées."
            
            # Annoncer la fin de l'événement
            if channel_waiting:
                await channel_waiting.send(f"@everyone 🛑 L'événement **'{event_name}'** est maintenant terminé. Merci à tous d'avoir participé !")

            # Les boutons sont supprimés en passant view=None
            await event_message.edit(embed=embed, view=None)

        except Exception as e:
            print(f"Erreur lors de la mise à jour du message de fin d'événement : {e}")
    else:
        # Si le message n'est pas trouvé, envoie un message de confirmation
        if channel_waiting:
            try:
                await channel_waiting.send(f"L'événement **'{event_name}'** a été terminé, mais le message original a été supprimé. Les rôles ont été retirés aux participants.", delete_after=60)
            except discord.Forbidden:
                print(f"Permissions insuffisantes pour envoyer un message dans le canal {channel_waiting.name}.")
            except Exception as e:
                print(f"Erreur lors de l'envoi du message de confirmation : {e}")


    # Suppression de l'événement de Firestore.
    await asyncio.to_thread(event_ref.delete)
    print(f"Événement '{event_name}' (ID: {event_doc_id}) supprimé de Firestore.")


@tasks.loop(seconds=15) # Fréquence du loop ajustée pour une vérification moins fréquente
async def update_event_messages():
    """Tâche en arrière-plan pour vérifier et mettre à jour les événements."""
    print("Vérification des événements en cours...")
    events_ref = db.collection('events')
    now = datetime.now(PARIS_TIMEZONE)
    active_events_docs = await asyncio.to_thread(events_ref.stream)
    
    docs_to_delete = []
    
    for doc in active_events_docs:
        event_data = doc.to_dict()
        event_id = doc.id
        event_end_time = event_data.get('end_time')
        event_start_time = event_data.get('start_time')
        
        guild = bot.get_guild(event_data.get('guild_id'))
        channel_waiting = guild.get_channel(event_data.get('channel_waiting_id')) if guild else None
        
        # Gérer la fin de l'événement
        if event_end_time and event_end_time.astimezone(PARIS_TIMEZONE) < now:
            print(f"Événement '{event_data.get('name', event_id)}' expiré. Fin de l'événement...")
            await _end_event(event_id, channel_waiting)
            docs_to_delete.append(event_id)
            continue
            
        # Gérer le début de l'événement
        if event_start_time and event_start_time.astimezone(PARIS_TIMEZONE) <= now and not event_data.get('has_started'):
            print(f"Événement '{event_data.get('name', event_id)}' a commencé.")
            if channel_waiting:
                await channel_waiting.send(f"@everyone 🚀 L'événement **'{event_data.get('name', 'Nom inconnu')}'** a commencé ! Bonne partie ! (Les inscriptions sont maintenant fermées.)")
            
            # Mettre à jour l'état de l'événement dans Firestore et fermer les inscriptions
            await asyncio.to_thread(doc.reference.update, {'has_started': True, 'registrations_closed': True})
            
            # Mettre à jour le message de l'événement
            try:
                message_id = event_data.get('message_id')
                if channel_waiting and message_id:
                    event_message = await channel_waiting.fetch_message(message_id)
                    embed = event_message.embeds[0]
                    embed.title = f"ÉVÉNEMENT EN COURS : {event_data.get('name', 'Nom inconnu').upper()}"
                    embed.description = f"L'événement a commencé. Il se terminera à <t:{int(event_end_time.timestamp())}:f>."
                    await event_message.edit(embed=embed, view=None)
            except discord.NotFound:
                print(f"Message de l'événement {event_data.get('name', event_id)} non trouvé pour la mise à jour de début.")
            except Exception as e:
                print(f"Erreur lors de la mise à jour du message de début d'événement : {e}")

    # Suppression des documents expirés de Firestore.
    for doc_id in docs_to_delete:
        await asyncio.to_thread(db.collection('events').document(doc_id).delete)

# --- Commandes du bot ---


@bot.event
async def on_ready():
    """Événement appelé lorsque le bot est prêt."""
    print(f'Connecté en tant que {bot.user}')
    update_event_messages.start()


@bot.command(name='create_event')
async def create_event(ctx, name: str, duration_str: str, max_participants: int = 10, *, start_time_str: str = None):
    """
    Crée un nouvel événement avec une heure de début et une durée.
    Exemples :
    !create_event "Test Event" 1h 10
    !create_event "Late Night Raid" 30m 5 22:30
    """
    await ctx.message.delete()
    
    guild = ctx.guild
    
    try:
        duration_seconds = parse_duration(duration_str)
        if duration_seconds <= 0:
            await ctx.send("La durée doit être positive.", delete_after=60)
            return

        now = datetime.now(PARIS_TIMEZONE)
        
        if start_time_str:
            # Événement planifié
            try:
                start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
                event_start_time = PARIS_TIMEZONE.localize(datetime.combine(now.date(), start_time_obj))

                # Si l'heure de début est déjà passée aujourd'hui, planifier pour le lendemain
                if event_start_time < now:
                    event_start_time += timedelta(days=1)
                
            except ValueError:
                await ctx.send("Format de l'heure de début invalide. Utilisez le format `HH:MM` (ex: `20:30`).", delete_after=60)
                return
        else:
            # Événement immédiat
            event_start_time = now
            
        event_end_time = event_start_time + timedelta(seconds=duration_seconds)

        # Créer un rôle pour l'événement
        role = await guild.create_role(name=f"event-{name}", color=discord.Color.from_rgb(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
        
        # Définir les permissions pour le rôle
        await role.edit(mentionable=True)
        
        # Enregistrer l'événement dans Firestore
        new_event_ref = db.collection('events').document()
        event_data = {
            'name': name,
            'guild_id': guild.id,
            'creator_id': ctx.author.id,
            'message_id': None,
            'channel_waiting_id': ctx.channel.id,
            'role_id': role.id,
            'start_time': event_start_time,
            'end_time': event_end_time,
            'max_participants': max_participants,
            'participants': [],
            'has_started': False,
            'registrations_closed': False,
            'participant_label': 'participants'
        }
        await asyncio.to_thread(new_event_ref.set, event_data)
        
        # Créer l'embed et les boutons
        description = (
            f"**Début :** <t:{int(event_start_time.timestamp())}:f>\n"
            f"**Fin :** <t:{int(event_end_time.timestamp())}:f>\n\n"
            f"Cliquez sur le bouton **START** pour vous inscrire à l'événement !\n\n"
            f"@everyone Un nouvel événement est prêt à commencer ! Rejoignez-nous pour l'événement **'{name}'** !"
        )
        embed = create_retro_embed(f"PROCHAIN ÉVÉNEMENT : {name}", description=description)
        embed.add_field(name=f"Participants ({len(event_data['participants'])}/{max_participants} {event_data.get('participant_label', 'participants')})", value="Aucun participant", inline=False)
        
        view = EventButtons(new_event_ref.id)
        msg = await ctx.send(content=f"**{name.upper()}**", embed=embed, view=view)
        
        # Mettre à jour l'ID du message dans Firestore
        await asyncio.to_thread(new_event_ref.update, {'message_id': msg.id})
        
    except ValueError as e:
        await ctx.send(f"Erreur : {e}", delete_after=60)
        await asyncio.sleep(60)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Une erreur est survenue lors de la création de l'événement : `{e}`", delete_after=60)
        print(f"Erreur lors de la création de l'événement : {e}")


@bot.command(name='list_events')
async def list_events(ctx):
    """Affiche la liste des événements en cours et à venir."""
    await ctx.message.delete()
    events_ref = db.collection('events')
    events_docs = await asyncio.to_thread(events_ref.stream)
    
    embed = create_retro_embed("Liste des événements", color=NEON_BLUE)
    
    has_events = False
    for doc in events_docs:
        event_data = doc.to_dict()
        event_name = event_data.get('name', 'Nom inconnu')
        start_timestamp = int(event_data.get('start_time').timestamp())
        end_timestamp = int(event_data.get('end_time').timestamp())
        
        participants_count = len(event_data.get('participants', []))
        max_participants = event_data.get('max_participants', 'N/A')
        participant_label = event_data.get('participant_label', 'participants')
        
        status = "En cours" if event_data.get('has_started') else "Prévu"
        
        value = (
            f"**Status :** {status}\n"
            f"**Début :** <t:{start_timestamp}:f>\n"
            f"**Fin :** <t:{end_timestamp}:f>\n"
            f"**Participants :** {participants_count}/{max_participants} {participant_label}\n"
            f"**Salon :** <#{event_data.get('channel_waiting_id')}>"
        )
        embed.add_field(name=f"**- {event_name}**", value=value, inline=False)
        has_events = True
        
    if not has_events:
        embed.description = "Aucun événement en cours ou à venir."
        
    await ctx.send(embed=embed, delete_after=180)


# --- Fonctions pour le serveur web ---
# (Ajoutées pour permettre au bot de fonctionner en tant que Web Service)
app = Flask(__name__)


@app.route('/')
def home():
    return "Poxel bot is running!"


def run_flask_app():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


# --- Point d'entrée principal ---
def start_bot_and_webserver():
    # Démarrer le serveur web dans un thread séparé
    threading.Thread(target=run_flask_app).start()
    # Démarrer le bot Discord
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    start_bot_and_webserver()
