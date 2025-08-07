# coding=utf-8
import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import json
import os

# --- Configuration du bot ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- Variables globales pour le stockage en mémoire ---
events_en_cours = {}
messages_a_supprimer = []
TOKEN = os.getenv('DISCORD_TOKEN') # Utilise une variable d'environnement pour le token

# --- Fonctions utilitaires ---

def creer_embed(titre, description, couleur=0x009EFF, champs=None, image_url=None):
    """
    Crée et retourne un embed avec un style rétro-futuriste.
    """
    embed = discord.Embed(
        title=f"👾 💾 {titre} 💾 👾",
        description=description,
        color=couleur,
    )
    embed.set_author(name="Poxel Bot 🤖", icon_url="https://i.imgur.com/2U5yV1t.png")
    embed.set_footer(text="Système d'Event par Poxel - Version 1.0", icon_url="https://i.imgur.com/2U5yV1t.png")
    if champs:
        for nom, valeur, inline in champs:
            embed.add_field(name=nom, value=valeur, inline=inline)
    if image_url:
        embed.set_image(url=image_url)
    return embed

async def supprimer_messages_apres_delai():
    """
    Tâche en arrière-plan pour supprimer les messages de commandes.
    """
    while True:
        await asyncio.sleep(60)
        messages_a_supprimer_copie = messages_a_supprimer[:]
        for message in messages_a_supprimer_copie:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            finally:
                if message in messages_a_supprimer:
                    messages_a_supprimer.remove(message)

# --- Vues et composants d'interface utilisateur (boutons) ---

class CreateEventView(discord.ui.View):
    """
    Vue contenant les boutons pour rejoindre et quitter un événement.
    """
    def __init__(self, bot, event_name, role_id, channel_id, participant_nom, embed_message_id, event_duree):
        super().__init__(timeout=event_duree * 60)
        self.bot = bot
        self.event_name = event_name
        self.role_id = role_id
        self.channel_id = channel_id
        self.participant_nom = participant_nom
        self.embed_message_id = embed_message_id

    async def on_timeout(self):
        """
        Fonction appelée lorsque la vue expire.
        """
        self.stop()
        # Le reste de la logique de fin d'événement est géré par la fonction `finir_event`.

    @discord.ui.button(label="Rejoindre 🎮", style=discord.ButtonStyle.green, custom_id="join_button")
    async def join_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Gère le clic sur le bouton "Rejoindre".
        """
        event = events_en_cours.get(self.event_name)
        if not event:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True, delete_after=30)
            return

        if interaction.user.id in event['participants']:
            await interaction.response.send_message("Tu es déjà inscrit à cet événement !", ephemeral=True, delete_after=30)
            return

        modal = discord.ui.Modal(title=f"Pseudo pour l'événement '{self.event_name}'")
        modal.add_item(discord.ui.InputText(label="Pseudo en jeu (facultatif)", style=discord.InputTextStyle.short))
        
        async def on_submit_modal(interaction_modal: discord.Interaction):
            pseudo = interaction_modal.data.get('components', [{}])[0].get('components', [{}])[0].get('value', '').strip()
            
            role = interaction.guild.get_role(self.role_id)
            if role:
                await interaction_modal.user.add_roles(role)
            
            event['participants'][interaction_modal.user.id] = {
                'discord_id': interaction_modal.user.id,
                'discord_pseudo': interaction_modal.user.name,
                'pseudo_jeu': pseudo if pseudo else None,
            }
            
            embed_message = await interaction_modal.channel.fetch_message(self.embed_message_id)
            await mettre_a_jour_embed_event(embed_message, self.event_name)
            
            welcome_message = f"Bienvenue dans la partie {interaction_modal.user.mention}"
            if pseudo:
                welcome_message += f" ({pseudo})"
            await interaction_modal.response.send_message(welcome_message, ephemeral=True, delete_after=30)

        modal.on_submit = on_submit_modal
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Quitter 🚪", style=discord.ButtonStyle.red, custom_id="quit_button")
    async def quit_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Gère le clic sur le bouton "Quitter".
        """
        event = events_en_cours.get(self.event_name)
        if not event:
            await interaction.response.send_message("Cet événement n'existe plus.", ephemeral=True, delete_after=30)
            return

        if interaction.user.id not in event['participants']:
            await interaction.response.send_message("Tu n'es pas inscrit à cet événement.", ephemeral=True, delete_after=30)
            return

        role = interaction.guild.get_role(self.role_id)
        if role:
            await interaction.user.remove_roles(role)
        
        del event['participants'][interaction.user.id]
        
        embed_message = await interaction.channel.fetch_message(self.embed_message_id)
        await mettre_a_jour_embed_event(embed_message, self.event_name)

        await interaction.response.send_message(f"{interaction.user.mention} a quitté l'événement '{self.event_name}'.", ephemeral=True, delete_after=30)


async def mettre_a_jour_embed_event(message, event_name):
    """
    Met à jour l'embed de l'événement avec la liste des participants en temps réel.
    """
    event = events_en_cours.get(event_name)
    if not event:
        return

    participants_str = ""
    for participant_info in event['participants'].values():
        pseudo_jeu = participant_info['pseudo_jeu'] if participant_info['pseudo_jeu'] else "N/A"
        participants_str += f"> `👾` {participant_info['discord_pseudo']} (pseudo: {pseudo_jeu})\n"
    
    participants_str = participants_str if participants_str else "Aucun participant pour l'instant."

    embed = creer_embed(
        f"new event: {event_name}",
        f"Durée: {event['duree']} minutes\n"
        f"Point de ralliement: <#{event['salon_attente_id']}>\n"
        f"Il y a actuellement `{len(event['participants'])}` {event['participant_nom']}(s) inscrit(s).\n\n"
        f"Le rôle <@&{event['role_id']}> vous sera attribué une fois inscrit. Veuillez rejoindre le point de ralliement et patienter d’être déplacé dans le salon.",
        champs=[
            (f"Liste des {event['participant_nom']}(s)", participants_str, False)
        ]
    )

    await message.edit(embed=embed)


async def creer_event_maintenant(ctx, role_name, channel_name, duree, event_name, participant_nom):
    """
    Fonction principale pour créer un événement immédiat.
    """
    if event_name in events_en_cours:
        await ctx.send(f"❌ L'événement '{event_name}' existe déjà.", delete_after=60)
        return

    try:
        role = await ctx.guild.create_role(name=role_name, color=0x009EFF)
        salon = await ctx.guild.create_text_channel(
            channel_name, 
            overwrites={
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                role: discord.PermissionOverwrite(read_messages=True),
                ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
        )
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions nécessaires pour créer des rôles/salons.", delete_after=60)
        return

    embed_message = await ctx.send("@everyone")
    view = CreateEventView(bot, event_name, role.id, salon.id, participant_nom, embed_message.id, duree)
    
    events_en_cours[event_name] = {
        'type': 'immédiat',
        'nom': event_name,
        'role_id': role.id,
        'salon_attente_id': salon.id,
        'duree': duree,
        'participant_nom': participant_nom,
        'participants': {},
        'embed_message_id': embed_message.id
    }
    
    await mettre_a_jour_embed_event(embed_message, event_name)
    await embed_message.edit(view=view)

    bot.loop.create_task(finir_event_apres_delai(event_name, duree * 60))

    await ctx.send(f"✅ L'événement '{event_name}' a été créé ! Il commencera dans {duree} minutes.")


async def finir_event(event_name, guild):
    """
    Fonction pour gérer la fin d'un événement.
    """
    if event_name not in events_en_cours:
        return
    
    event = events_en_cours[event_name]
    embed_message_id = event.get('embed_message_id')
    
    try:
        role = guild.get_role(event['role_id'])
        salon = guild.get_channel(event['salon_attente_id'])

        for participant_id in event['participants']:
            member = guild.get_member(participant_id)
            if member and role:
                await member.remove_roles(role)

        if salon:
            await salon.delete()
        if role:
            await role.delete()

        if guild.system_channel:
            await guild.system_channel.send(f"@everyone 🕰️ L'événement '{event_name}' est maintenant terminé !")

        if embed_message_id:
            try:
                message = await guild.system_channel.fetch_message(embed_message_id)
                await message.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
    
    except discord.Forbidden:
        if guild.system_channel:
            await guild.system_channel.send("❌ Je n'ai pas les permissions pour nettoyer les rôles et salons.")

    del events_en_cours[event_name]
    

async def finir_event_apres_delai(event_name, delai_secondes):
    """
    Attend un certain temps puis appelle la fonction de fin d'événement.
    """
    await asyncio.sleep(delai_secondes)
    guild = bot.guilds[0]
    await finir_event(event_name, guild)


# --- Commandes du bot ---

def has_manage_roles():
    """
    Décorateur de vérification de permissions.
    """
    async def predicate(ctx):
        return ctx.author.guild_permissions.manage_roles
    return commands.check(predicate)


@bot.event
async def on_ready():
    """
    Indique que le bot est prêt et démarre la tâche de suppression de messages.
    """
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    bot.loop.create_task(supprimer_messages_apres_delai())


@bot.command(name='create_event')
@has_manage_roles()
async def create_event(ctx, event_name, participant_nom, role_name, channel_name, duree: int):
    """
    Crée un événement immédiat.
    Exemple: !create_event "Chasse au dragon" joueur "Chasseurs" "salle-des-chasseurs" 60
    """
    await ctx.message.delete(delay=60)
    await creer_event_maintenant(ctx, role_name, channel_name, duree, event_name, participant_nom)


@bot.command(name='create_event_plan')
@has_manage_roles()
async def create_event_plan(ctx, event_name, participant_nom, role_name, channel_name, duree: int, date_str, heure_str):
    """
    Planifie un événement à une date et heure précises.
    Exemple: !create_event_plan "Tournoi de foot" footballeur "Footballeurs" "stade-de-foot" 120 2025-08-08 20:00
    """
    await ctx.message.delete(delay=60)
    
    try:
        date_planifiee = datetime.strptime(f"{date_str} {heure_str}", "%Y-%m-%d %H:%M")
        maintenant = datetime.now()
        delai_secondes = (date_planifiee - maintenant).total_seconds()
        
        if delai_secondes < 0:
            await ctx.send("❌ La date et l'heure de planification sont dans le passé.", delete_after=60)
            return

        await ctx.send(f"✅ L'événement '{event_name}' est planifié pour le {date_planifiee.strftime('%d/%m/%Y à %H:%M')}.", delete_after=60)

        await asyncio.sleep(delai_secondes)
        
        await creer_event_maintenant(ctx, role_name, channel_name, duree, event_name, participant_nom)
    
    except ValueError:
        await ctx.send("❌ Format de date/heure incorrect. Utilisez YYYY-MM-DD HH:MM", delete_after=60)


@bot.command(name='end_event')
@has_manage_roles()
async def end_event(ctx, event_name):
    """
    Termine manuellement un événement immédiat.
    Exemple: !end_event "Chasse au dragon"
    """
    await ctx.message.delete(delay=60)
    if event_name in events_en_cours and events_en_cours[event_name]['type'] == 'immédiat':
        await ctx.send(f"📢 L'événement '{event_name}' va être terminé manuellement.", delete_after=60)
        await finir_event(event_name, ctx.guild)
    else:
        await ctx.send(f"❌ L'événement '{event_name}' n'est pas un événement immédiat actif.", delete_after=60)


@bot.command(name='end_event_plan')
@has_manage_roles()
async def end_event_plan(ctx, event_name):
    """
    Termine manuellement un événement planifié.
    Exemple: !end_event_plan "Tournoi de foot"
    """
    await ctx.message.delete(delay=60)
    if event_name in events_en_cours and events_en_cours[event_name]['type'] == 'planifié':
        await ctx.send(f"📢 L'événement planifié '{event_name}' va être terminé manuellement.", delete_after=60)
        await finir_event(event_name, ctx.guild)
    else:
        await ctx.send(f"❌ L'événement '{event_name}' n'est pas un événement planifié actif.", delete_after=60)


@bot.command(name='list_events')
async def list_events(ctx):
    """
    Affiche tous les événements actifs.
    """
    await ctx.message.delete(delay=60)
    if not events_en_cours:
        await ctx.send("Aucun événement actif pour le moment.", delete_after=60)
        return

    description = "Voici la liste des événements actuellement en cours ou planifiés :\n\n"
    for event_name, event_data in events_en_cours.items():
        participants = len(event_data['participants'])
        role = ctx.guild.get_role(event_data['role_id'])
        salon = ctx.guild.get_channel(event_data['salon_attente_id'])
        
        description += (
            f"**`{event_name}`**\n"
            f"  > **Type** : {event_data['type']}\n"
            f"  > **Participants** : {participants} {event_data['participant_nom']}(s)\n"
            f"  > **Rôle** : {role.mention if role else 'Non trouvé'}\n"
            f"  > **Salon** : {salon.mention if salon else 'Non trouvé'}\n"
        )
    
    embed = creer_embed("Events en cours", description)
    await ctx.send(embed=embed, delete_after=60)

# --- Système d'aide personnalisé ---

@bot.group(name='helpoxel', invoke_without_command=True)
async def helpoxel(ctx):
    """
    Affiche la liste des commandes disponibles.
    """
    await ctx.message.delete(delay=60)
    description = (
        "🤖 **Bienvenue dans le manuel de Poxel !** 🤖\n"
        "Utilise `!helpoxel <commande>` pour plus de détails sur une commande spécifique.\n\n"
        "**Commandes d'événement :**\n"
        " - `!create_event` : Crée un événement qui démarre immédiatement.\n"
        " - `!create_event_plan` : Planifie un événement à une date et heure précises.\n"
        " - `!end_event` : Termine manuellement un événement immédiat.\n"
        " - `!end_event_plan` : Termine manuellement un événement planifié.\n"
        " - `!list_events` : Affiche les événements actifs.\n"
    )
    embed = creer_embed("Manuel de Poxel", description)
    await ctx.send(embed=embed, delete_after=300)

@helpoxel.command(name='create_event')
async def help_create_event(ctx):
    """
    Aide pour la commande create_event.
    """
    await ctx.message.delete(delay=60)
    embed = creer_embed(
        "Manuel de Poxel : !create_event",
        "**Usage** : `!create_event <nom_event> <nom_participant> <nom_role> <nom_salon> <durée_en_min>`\n"
        "**Exemple** : `!create_event \"Chasse au trésor\" chasseur \"Aventuriers\" \"chasse-au-tresor\" 60`\n\n"
        "Crée un événement qui démarre immédiatement avec un rôle et un salon dédiés. Les participants rejoignent via un bouton et le rôle leur donne accès au salon. L'événement se termine automatiquement après la durée spécifiée."
    )
    await ctx.send(embed=embed, delete_after=300)

@helpoxel.command(name='create_event_plan')
async def help_create_event_plan(ctx):
    """
    Aide pour la commande create_event_plan.
    """
    await ctx.message.delete(delay=60)
    embed = creer_embed(
        "Manuel de Poxel : !create_event_plan",
        "**Usage** : `!create_event_plan <nom_event> <nom_participant> <nom_role> <nom_salon> <durée_en_min> <YYYY-MM-DD> <HH:MM>`\n"
        "**Exemple** : `!create_event_plan \"Tournoi de foot\" footballeur \"Footballeurs\" \"stade-de-foot\" 120 2025-08-08 20:00`\n\n"
        "Planifie un événement à une date et heure précises. L'événement démarre automatiquement à l'heure prévue et se termine après la durée spécifiée."
    )
    await ctx.send(embed=embed, delete_after=300)


# --- Démarrage du bot ---
@bot.event
async def on_ready():
    """
    Indique que le bot est prêt et démarre la tâche de suppression de messages.
    """
    print(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    bot.loop.create_task(supprimer_messages_apres_delai())

if __name__ == '__main__':
    bot.run(TOKEN)
