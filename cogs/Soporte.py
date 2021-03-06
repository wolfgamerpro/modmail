import asyncio
import re
from datetime import datetime
from itertools import zip_longest
from typing import Optional, Union
from types import SimpleNamespace

import discord
from discord.ext import commands
from discord.utils import escape_markdown

from dateutil import parser
from natural.date import duration

from core import checks
from core.models import PermissionLevel, getLogger
from core.paginator import EmbedPaginatorSession
from core.thread import Thread
from core.time import UserFriendlyTime, human_timedelta
from core.utils import *

logger = getLogger(__name__)


class Soporte(commands.Cog):
    """Comandos directamente relacionados con la funcionalidad de Soporte."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @trigger_typing
    @checks.has_permissions(PermissionLevel.OWNER)
    async def setup(self, ctx):
        """
        Configura un servidor para RequiemSupport.
        Solo necesitas ejecutar este comando
        una vez después de configurar RequiemSupport.
        """

        if ctx.guild != self.bot.modmail_guild:
            return await ctx.send(
                f"Solo puedes configurar en el servidor de RequiemSupport: {self.bot.modmail_guild}."
            )

        if self.bot.main_category is not None:
            logger.debug("No se puede volver a configurar el servidor, se encontró main_category")
            return await ctx.send(f"{self.bot.modmail_guild} ya está configurado.")

        if self.bot.modmail_guild is None:
            embed = discord.Embed(
                title="Error",
                description="No se encontró el servidor en funcionamiento de RequiemSupport.",
                color=self.bot.error_color,
            )
            return await ctx.send(embed=embed)

        overwrites = {
            self.bot.modmail_guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.bot.modmail_guild.me: discord.PermissionOverwrite(read_messages=True),
        }

        for level in PermissionLevel:
            if level <= PermissionLevel.REGULAR:
                continue
            permissions = self.bot.config["level_permissions"].get(level.name, [])
            for perm in permissions:
                perm = int(perm)
                if perm == -1:
                    key = self.bot.modmail_guild.default_role
                else:
                    key = self.bot.modmail_guild.get_member(perm)
                    if key is None:
                        key = self.bot.modmail_guild.get_role(perm)
                if key is not None:
                    logger.info("Otorgar acceso %s a RequiemSupport.", key.name)
                    overwrites[key] = discord.PermissionOverwrite(read_messages=True)

        category = await self.bot.modmail_guild.create_category(
            name="RequiemSupport", overwrites=overwrites
        )

        await category.edit(position=0)

        log_channel = await self.bot.modmail_guild.create_text_channel(
            name="「📜」┆˹registro˼", category=category
        )

        self.bot.config["main_category_id"] = category.id
        self.bot.config["log_channel_id"] = log_channel.id

        await self.bot.config.update()
        await ctx.send(
            "**Se configuró el servidor correctamente.**\n"
            "Considere establecer niveles de permisos para otorgar acceso a roles "
            "o ha los usuarios la capacidad de utilizar RequiemSupport.\n\n"
            f"Usa:\n- `{self.bot.prefix}permissions` y `{self.bot.prefix}permissions add` "
            "para obtener más información sobre la configuración de permisos.\n"
            f"- `{self.bot.prefix}config help` para obtener una lista de las configuraciónes disponibles."
        )

        if not self.bot.config["command_permissions"] and not self.bot.config["level_permissions"]:
            await self.bot.update_perms(PermissionLevel.REGULAR, -1)
            for owner_id in self.bot.bot_owner_ids:
                await self.bot.update_perms(PermissionLevel.OWNER, owner_id)

    @commands.group(aliases=["snippets"], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet(self, ctx, *, nombre: str.lower = None):
        """
        Cree mensajes predefinidos para usar en tickets.
        Cuando se utiliza solo "{prefix}snippet", se obtiene
        una lista de snippets que están configurados actualmente.
        `{prefix}snippet-name` mostrará a lo que apuntan los snippets.
        Para crear un snippet:
        - `{prefix}snippet add snippet-name Un texto predefinido.`
        Puedes usar tu snippet en un canal de tickets.
        con `{prefix}snippet-name`, el mensaje "Un texto predefinido"
        Será enviado al destinatario.
        Actualmente, no hay un comando de snippet anónimo incorporado;
        sin embargo, una solución está disponible usando `{prefix}alias`. 
        Así es cómo:
        - `{prefix}alias add snippet-name anonreply Un texto anónimo predefinido.`
        Ver también `{prefix}alias`.
        """

        if name is not None:
            val = self.bot.snippets.get(name)
            if val is None:
                embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
            else:
                embed = discord.Embed(
                    title=f'Snippet - "{name}":', description=val, color=self.bot.main_color
                )
            return await ctx.send(embed=embed)

        if not self.bot.snippets:
            embed = discord.Embed(
                color=self.bot.error_color, description="You dont have any snippets at the moment."
            )
            embed.set_footer(text=f'Check "{self.bot.prefix}help snippet add" to add a snippet.')
            embed.set_author(name="Snippets", icon_url=ctx.guild.icon_url)
            return await ctx.send(embed=embed)

        embeds = []

        for i, names in enumerate(zip_longest(*(iter(sorted(self.bot.snippets)),) * 15)):
            description = format_description(i, names)
            embed = discord.Embed(color=self.bot.main_color, description=description)
            embed.set_author(name="Snippets", icon_url=ctx.guild.icon_url)
            embeds.append(embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @snippet.command(name="raw")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_raw(self, ctx, *, nombre: str.lower):
        """
        Ver el contenido sin procesar de un snippet.
        """
        val = self.bot.snippets.get(name)
        if val is None:
            embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
        else:
            val = truncate(escape_code_block(val), 2048 - 7)
            embed = discord.Embed(
                title=f'Raw snippet - "{name}":',
                description=f"```\n{val}```",
                color=self.bot.main_color,
            )

        return await ctx.send(embed=embed)

    @snippet.command(name="add")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_add(self, ctx, nombre: str.lower, *, valor: commands.clean_content):
        """
        Agrega un snippet.
        Simplemente para agregar un snippet, haga lo siguiente: ```
        {prefix}snippet add hey Hola a todos :)
        ```
        entonces cuando escribes `{prefix}hey`, "Hola a todos :)"
        será enviado al destinatario.
        Para agregar un nombre de snippet de varias palabras, use comillas: ```
        {prefix}snippet add "dos palabras" este es un snippet de dos palabras.
        ```
        """
        if name in self.bot.snippets:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"Snippet `{name}` ya existe.",
            )
            return await ctx.send(embed=embed)

        if name in self.bot.aliases:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"Existe un alias que comparte el mismo nombre: `{name}`.",
            )
            return await ctx.send(embed=embed)

        if len(name) > 120:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description="Los nombres de los snippets no pueden tener más de 120 caracteres.",
            )
            return await ctx.send(embed=embed)

        self.bot.snippets[name] = value
        await self.bot.config.update()

        embed = discord.Embed(
            title="Added snippet",
            color=self.bot.main_color,
            description="Snippet creado con éxito.",
        )
        return await ctx.send(embed=embed)

    @snippet.command(name="remove", aliases=["del", "delete"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_remove(self, ctx, *, nombre: str.lower):
        """Remove a snippet."""

        if name in self.bot.snippets:
            embed = discord.Embed(
                title="Snippet eliminado",
                color=self.bot.main_color,
                description=f"Snippet `{name}` ahora está eliminado.",
            )
            self.bot.snippets.pop(name)
            await self.bot.config.update()
        else:
            embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
        await ctx.send(embed=embed)

    @snippet.command(name="edit")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_edit(self, ctx, nombre: str.lower, *, valor):
        """
        Edite un snippet.
        Para editar un nombre de snippet de varias palabras, use comillas: ```
        {prefix}snippet edit "dos palabras" este es un nuevo snippet de dos palabras.
        ```
        """
        if name in self.bot.snippets:
            self.bot.snippets[name] = value
            await self.bot.config.update()

            embed = discord.Embed(
                title="Snippet editado",
                color=self.bot.main_color,
                description=f'`{name}` ahora enviará "{value}".',
            )
        else:
            embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
        await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @checks.thread_only()
    async def move(self, ctx, categoría: discord.CategoryChannel, *, detalles: str = None):
        """
        Mover un ticket a otra categoría.
        `categoría` puede ser un ID de categoría, una mención o un nombre.
        `detalles` es una cadena que incluye argumentos sobre cómo realizar el movimiento. Ej.: "en silencio"
        """
        thread = ctx.thread
        silent = False

        if specifics:
            silent_words = ["silent", "silently"]
            silent = any(word in silent_words for word in specifics.split())

        await thread.channel.edit(category=category, sync_permissions=True)

        if self.bot.config["thread_move_notify"] and not silent:
            embed = discord.Embed(
                title="Ticket movido",
                description=self.bot.config["thread_move_response"],
                color=self.bot.main_color,
            )
            await thread.recipient.send(embed=embed)

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    async def send_scheduled_close_message(self, ctx, after, silent=False):
        human_delta = human_timedelta(after.dt)

        silent = "*silenciado* " if silent else ""

        embed = discord.Embed(
            title="Cierre programado",
            description=f"Este ticket se cerrará {silent} en {human_delta}.",
            color=self.bot.error_color,
        )

        if after.arg and not silent:
            embed.add_field(name="Mensaje", value=after.arg)

        embed.set_footer(text="El cierre se cancelará si se envía un mensaje de conversación.")
        embed.timestamp = after.dt

        await ctx.send(embed=embed)

    @commands.command(usage="[tiempo] [mensaje de cierre]")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def close(self, ctx, *, after: UserFriendlyTime = None):
        """
        Cierra el ticket actual.
        Cerrar después de un período de tiempo:
        - `{prefix}close in 5 hours`
        - `{prefix}close 2m30s`
        Mensajes de cierre personalizados:
        - `{prefix}close 2 hours El problema ha sido resuelto.`
        - `{prefix}close Nos pondremos en contacto contigo una vez que sepamos más.`
        Cerrar un ticket en silencio (sin mensaje)
        - `{prefix}close silently`
        - `{prefix}close in 10m silently`
        Evita que un ticket se cierre:
        - `{prefix}close cancel`
        """

        thread = ctx.thread

        now = datetime.utcnow()

        close_after = (after.dt - now).total_seconds() if after else 0
        message = after.arg if after else None
        silent = str(message).lower() in {"silent", "silently"}
        cancel = str(message).lower() == "cancel"

        if cancel:

            if thread.close_task is not None or thread.auto_close_task is not None:
                await thread.cancel_closure(all=True)
                embed = discord.Embed(
                    color=self.bot.error_color, description="Se canceló el cierre programado."
                )
            else:
                embed = discord.Embed(
                    color=self.bot.error_color,
                    description="Este ticket aún no está programado para cerrarse.",
                )

            return await ctx.send(embed=embed)

        if after and after.dt > now:
            await self.send_scheduled_close_message(ctx, after, silent)

        await thread.close(closer=ctx.author, after=close_after, message=message, silent=silent)

    @staticmethod
    def parse_user_or_role(ctx, Usuario_O_Rol):
        mention = None
        if Usuario_O_Rol is None:
            mention = ctx.author.mention
        elif hasattr(Usuario_O_Rol, "mention"):
            mention = Usuario_O_Rol.mention
        elif Usuario_O_Rol in {"here", "everyone", "@here", "@everyone"}:
            mention = "@" + Usuario_O_Rol.lstrip("@")
        return mention

    @commands.command(aliases=["alert"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def notify(
        self, ctx, *, Usuario_O_Rol: Union[discord.Role, User, str.lower, None] = None
    ):
        """
        Notificar a un usuario o rol cuando se reciba el siguiente ticket.
        Una vez que se recibe un ticket, se hará ping una vez a `Usuario_O_Rol`.
        Deje `Usuario_O_Rol` vacío para notificarse.
        `Usuario_O_Rol` puede ser una ID de usuario/rol, mención, nombre, "everyone", o "here".
        """
        mention = self.parse_user_or_role(ctx, Usuario_O_Rol)
        if mention is None:
            raise commands.BadArgument(f"{Usuario_O_Rol} No es un usuario o rol válido.")

        thread = ctx.thread

        if str(thread.id) not in self.bot.config["notification_squad"]:
            self.bot.config["notification_squad"][str(thread.id)] = []

        mentions = self.bot.config["notification_squad"][str(thread.id)]

        if mention in mentions:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{mention} ya se va a mencionar.",
            )
        else:
            mentions.append(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color,
                description=f"{mention} se mencionará en el siguiente ticket.",
            )
        return await ctx.send(embed=embed)

    @commands.command(aliases=["unalert"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def unnotify(
        self, ctx, *, Usuario_O_Rol: Union[discord.Role, User, str.lower, None] = None
    ):
        """
        Anule la notificación a un usuario, rol o usted mismo de un ticket.
        Deje `Usuario_O_Rol` vacío para anular la notificación.
        `Usuario_O_Rol` puede ser una ID de usuario/rol, mención, nombre, "everyone", o "here".
        """
        mention = self.parse_user_or_role(ctx, Usuario_O_Rol)
        if mention is None:
            mention = f"`{Usuario_O_Rol}`"

        thread = ctx.thread

        if str(thread.id) not in self.bot.config["notification_squad"]:
            self.bot.config["notification_squad"][str(thread.id)] = []

        mentions = self.bot.config["notification_squad"][str(thread.id)]

        if mention not in mentions:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{mention} no tiene una notificación pendiente.",
            )
        else:
            mentions.remove(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color, description=f"{mention} ya no será notificado."
            )
        return await ctx.send(embed=embed)

    @commands.command(aliases=["sub"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def subscribe(
        self, ctx, *, Usuario_O_Rol: Union[discord.Role, User, str.lower, None] = None
    ):
        """
        Notifique a un usuario, rol o usted mismo por cada ticket.
        
        Se le hará ping por cada ticket hasta que cancele la suscripción.
        Deje `Usuario_O_Rol` vacío para notificarse.
        `Usuario_O_Rol` puede ser una ID de usuario/rol, mención, nombre, "everyone", o "here".
        """
        mention = self.parse_user_or_role(ctx, Usuario_O_Rol)
        if mention is None:
            raise commands.BadArgument(f"{Usuario_O_Rol} No es un usuario o rol válido.")

        thread = ctx.thread

        if str(thread.id) not in self.bot.config["subscriptions"]:
            self.bot.config["subscriptions"][str(thread.id)] = []

        mentions = self.bot.config["subscriptions"][str(thread.id)]

        if mention in mentions:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{mention} no está suscrito a este ticket.",
            )
        else:
            mentions.append(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color,
                description=f"{mention} ahora será notificado en todos los tickets.",
            )
        return await ctx.send(embed=embed)

    @commands.command(aliases=["unsub"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def unsubscribe(
        self, ctx, *, Usuario_O_Rol: Union[discord.Role, User, str.lower, None] = None
    ):
        """
        Cancelar la suscripción de un usuario, rol o usted mismo de un ticket.
        Deje `Usuario_O_Rol` vacío para anular la notificación.
        `Usuario_O_Rol` puede ser una ID de usuario/rol, mención, nombre, "everyone", o "here".
        """
        mention = self.parse_user_or_role(ctx, Usuario_O_Rol)
        if mention is None:
            mention = f"`{Usuario_O_Rol}`"

        thread = ctx.thread

        if str(thread.id) not in self.bot.config["subscriptions"]:
            self.bot.config["subscriptions"][str(thread.id)] = []

        mentions = self.bot.config["subscriptions"][str(thread.id)]

        if mention not in mentions:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{mention} no está suscrito a este ticket.",
            )
        else:
            mentions.remove(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color,
                description=f"{mention} ahora se ha cancelado la suscripción a este ticket.",
            )
        return await ctx.send(embed=embed)
    
    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def loglink(self, ctx):
        """Obtiene el enlace a los registros del ticket actual."""
        log_link = await self.bot.api.get_log_link(ctx.channel.id)
        await ctx.send(embed=discord.Embed(color=self.bot.main_color, description=log_link))

    def format_log_embeds(self, logs, avatar_url):
        embeds = []
        logs = tuple(logs)
        title = f"Resultados totales encontrados: ({len(logs)})"

        for entry in logs:
            created_at = parser.parse(entry["created_at"])

            prefix = self.bot.config["log_url_prefix"].strip("/")
            if prefix == "NONE":
                prefix = ""
            log_url = f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{entry['key']}"

            username = entry["recipient"]["name"] + "#"
            username += entry["recipient"]["discriminator"]

            embed = discord.Embed(color=self.bot.main_color, timestamp=created_at)
            embed.set_author(name=f"{title} - {username}", icon_url=avatar_url, url=log_url)
            embed.url = log_url
            embed.add_field(name="Creado hace", value=duration(created_at, now=datetime.utcnow()))
            closer = entry.get("closer")
            if closer is None:
                closer_msg = "Unknown"
            else:
                closer_msg = f"<@{closer['id']}>"
            embed.add_field(name="Cerrado por", value=closer_msg)

            if entry["recipient"]["id"] != entry["creator"]["id"]:
                embed.add_field(name="Creado por", value=f"<@{entry['creator']['id']}>")

            embed.add_field(name="Vista previa", value=format_preview(entry["messages"]), inline=False)

            if closer is not None:
                # BUG: Currently, logviewer can't display logs without a closer.
                embed.add_field(name="Link", value=log_url)
            else:
                logger.debug("Entrada de registro no válido: no cerrado.")
                embed.add_field(name="Clave de registro", value=f"`{entry['key']}`")

            embed.set_footer(text="ID del destinatario: " + str(entry["recipient"]["id"]))
            embeds.append(embed)
        return embeds

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs(self, ctx, *, user: User = None):
        """
        Obtener registros de tickets anteriores de un miembro.
        Deje `user` en blanco cuando este comando se utilice dentro de un
        canal de ticket para mostrar los registros del destinatario actual.
        `user` puede ser la ID de usuario, una mención o un nombre.
        """

        await ctx.trigger_typing()

        if not user:
            thread = ctx.thread
            if not thread:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="member"))
            user = thread.recipient

        default_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"
        icon_url = getattr(user, "avatar_url", default_avatar)

        logs = await self.bot.api.get_user_logs(user.id)

        if not any(not log["open"] for log in logs):
            embed = discord.Embed(
                color=self.bot.error_color,
                description="Este usuario no tiene registros anteriores.",
            )
            return await ctx.send(embed=embed)

        logs = reversed([log for log in logs if not log["open"]])

        embeds = self.format_log_embeds(logs, avatar_url=icon_url)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @logs.command(name="closed-by", aliases=["closeby"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs_closed_by(self, ctx, *, user: User = None):
        """
        Obtiene todos los registros cerrados por el usuario especificado.
        Si no se proporciona el `user`, el usuario será la persona que envió este comando.
        `user` puede ser la ID de usuario, una mención o un nombre.
        """
        user = user if user is not None else ctx.author

        entries = await self.bot.api.search_closed_by(user.id)
        embeds = self.format_log_embeds(entries, avatar_url=self.bot.guild.icon_url)

        if not embeds:
            embed = discord.Embed(
                color=self.bot.error_color,
                description="No se han encontrado entradas de registro para esa consulta.",
            )
            return await ctx.send(embed=embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @logs.command(name="delete", aliases=["wipe"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def logs_delete(self, ctx, key_or_link: str):
        """
        Borra una entrada de registro de la base de datos.
        """
        key = key_or_link.split("/")[-1]

        success = await self.bot.api.delete_log_entry(key)

        if not success:
            embed = discord.Embed(
                title="Error",
                description=f"Entrada de registro`{key}` no encontrada.",
                color=self.bot.error_color,
            )
        else:
            embed = discord.Embed(
                title="Éxito",
                description=f"Entrada de registro`{key}` eliminada correctamente.",
                color=self.bot.main_color,
            )

        await ctx.send(embed=embed)

    @logs.command(name="responded")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs_responded(self, ctx, *, user: User = None):
        """
        Obtenga todos los registros donde el usuario especificado haya respondido al menos una vez.
        Si no se proporciona el `user`, el usuario será la persona que envió este comando.
        `user` puede ser la ID de usuario, una mención o un nombre.
        """
        user = user if user is not None else ctx.author

        entries = await self.bot.api.get_responded_logs(user.id)

        embeds = self.format_log_embeds(entries, avatar_url=self.bot.guild.icon_url)

        if not embeds:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{getattr(user, 'mention', user.id)} has not responded to any threads.",
            )
            return await ctx.send(embed=embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @logs.command(name="search", aliases=["find"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs_search(self, ctx, límite: Optional[int] = None, *, busqueda):
        """
        Recupera todos los registros que contienen mensajes especificados.
        Proporcione un "límite" para especificar el número máximo de registros que el bot debe encontrar.
        """

        await ctx.trigger_typing()

        entries = await self.bot.api.search_by_text(busqueda, límite)

        embeds = self.format_log_embeds(entries, avatar_url=self.bot.guild.icon_url)

        if not embeds:
            embed = discord.Embed(
                color=self.bot.error_color,
                description="No log entries have been found for that query.",
            )
            return await ctx.send(embed=embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def reply(self, ctx, *, mensaje: str = ""):
        """
        Responder a un ticket de RequiemSupport.
        Admite archivos adjuntos e imágenes, así como
        embed automático a las URL de imágenes.
        """
        ctx.message.content = mensaje
        async with ctx.typing():
            await ctx.thread.reply(ctx.message)

    @commands.command(aliases=["formatreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def freply(self, ctx, *, mensaje: str = ""):
        """
        Responder a un ticket de RequiemSupport con variables.
        Funciona igual que `{prefix}reply`, sin embargo con la adición de tres variables:
          - `{{channel}}` - El objeto `discord.TextChannel`
          - `{{recipient}}` - El objeto del destinatario `discord.User`
          - `{{author}}` - El objeto del autor `discord.User`
        Admite archivos adjuntos e imágenes, así como
        embed automático a las URL de imágenes.
        """
        mensaje = self.bot.formatter.format(
            mensaje, channel=ctx.channel, recipient=ctx.thread.recipient, author=ctx.message.author
        )
        ctx.message.content = mensaje
        async with ctx.typing():
            await ctx.thread.reply(ctx.message)

    @commands.command(aliases=["anonreply", "anonymousreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def areply(self, ctx, *, mensaje: str = ""):
        """
        Responder a un ticket de forma anónima.
        Puede editar el nombre del usuario anónimo,
        avatar y etiqueta usando el comando config.
        Edite `anon_username`, `anon_avatar_url` `anon_tag`.
        """
        ctx.message.content = mensaje
        async with ctx.typing():
            await ctx.thread.reply(ctx.message, anonymous=True)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def note(self, ctx, *, mensaje: str = ""):
        """
        Toma nota sobre el ticket actual.
        Útil para señalar el contexto.
        """
        ctx.message.content = mensaje
        async with ctx.typing():
            mensaje = await ctx.thread.note(ctx.message)
            await mensaje.pin()

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def edit(self, ctx, mensaje_id: Optional[int] = None, *, mensaje: str):
        """
        Edite un mensaje que se envió mediante el comando responder o respuesta anónima.
        Si no se proporciona `mensaje_id`,
        se editará el último mensaje enviado por un Staff.
        Nota: los archivos adjuntos **no se pueden** editar.
        """
        thread = ctx.thread

        try:
            await thread.edit_message(mensaje_id, mensaje)
        except ValueError:
            return await ctx.send(
                embed=discord.Embed(
                    title="Fallido",
                    description="No se puede encontrar un mensaje para editar.",
                    color=self.bot.error_color,
                )
            )

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command(usage="<usuario> [categoría]")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def contact(
        self,
        ctx,
        user: Union[discord.Member, discord.User],
        *,
        category: discord.CategoryChannel = None,
    ):
        """
        Crea un ticket con un miembro especificado.
        Si se especifica `categoría`, el ticket
        se creará en esa categoría especificada.
        Si se especifica `categoría`, puede ser la ID de la categoría o un nombre.
        `usuario` puede ser la ID del usuario, una mención o un nombre.
        """

        if user.bot:
            embed = discord.Embed(
                color=self.bot.error_color, description="No se puede iniciar un ticket con un bot."
            )
            return await ctx.send(embed=embed)

        exists = await self.bot.threads.find(recipient=user)
        if exists:
            embed = discord.Embed(
                color=self.bot.error_color,
                description="Un ticket para este usuario ya "
                f"existe en {exists.channel.mention}.",
            )
            await ctx.channel.send(embed=embed)

        else:
            thread = await self.bot.threads.create(user, creator=ctx.author, category=category)
            if self.bot.config["dm_disabled"] >= 1:
                logger.info("Contacting user %s when Modmail DM is disabled.", user)

            embed = discord.Embed(
                title="Ticket Creado",
                description=f"Ticket iniciado por {ctx.author.mention} para {usuario.mention}.",
                color=self.bot.main_color,
            )
            await thread.wait_until_ready()
            await thread.channel.send(embed=embed)
            sent_emoji, _ = await self.bot.retrieve_emoji()
            await self.bot.add_reaction(ctx.message, sent_emoji)
            await asyncio.sleep(3)
            await ctx.message.delete()

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def blocked(self, ctx):
        """Obtiene una lista de usuarios bloqueados."""

        embeds = [discord.Embed(title="Usuarios Bloqueados", color=self.bot.main_color, description="")]

        users = []

        for id_, reason in self.bot.blocked_users.items():
            user = self.bot.get_user(int(id_))
            if user:
                users.append((user.mention, reason))
            else:
                try:
                    user = await self.bot.fetch_user(id_)
                    users.append((user.mention, reason))
                except discord.NotFound:
                    users.append((id_, reason))

        if users:
            embed = embeds[0]

            for mention, reason in users:
                line = mention + f" - {reason or 'No se proporcionó ninguna razón'}\n"
                if len(embed.description) + len(line) > 2048:
                    embed = discord.Embed(
                        title="Usuarios Bloqueados (Continuado)",
                        color=self.bot.main_color,
                        description=line,
                    )
                    embeds.append(embed)
                else:
                    embed.description += line
        else:
            embeds[0].description = "Actualmente no hay usuarios bloqueados."

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @blocked.command(name="whitelist")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def blocked_whitelist(self, ctx, *, user: User = None):
        """
        Incluya o elimine la lista blanca de un usuario para que no sea bloqueado.
        Útil para evitar que los usuarios sean bloqueados por restricciones account_age/guild_age.
        """
        if user is None:
            thread = ctx.thread
            if thread:
                user = thread.recipient
            else:
                return await ctx.send_help(ctx.command)

        mention = getattr(user, "mention", f"`{user.id}`")
        msg = ""

        if str(user.id) in self.bot.blocked_whitelisted_users:
            embed = discord.Embed(
                title="Éxito",
                description=f"{mention} ya no está en la lista blanca.",
                color=self.bot.main_color,
            )
            self.bot.blocked_whitelisted_users.remove(str(user.id))
            return await ctx.send(embed=embed)

        self.bot.blocked_whitelisted_users.append(str(user.id))

        if str(user.id) in self.bot.blocked_users:
            msg = self.bot.blocked_users.get(str(user.id)) or ""
            self.bot.blocked_users.pop(str(user.id))

        await self.bot.config.update()

        if msg.startswith("Mensaje del Sistema: "):
            # If the user is blocked internally (for example: below minimum account age)
            # Show an extended message stating the original internal message
            reason = msg[16:].strip().rstrip(".")
            embed = discord.Embed(
                title="Éxito",
                description=f"{mention} fue previamente bloqueado internamente por "
                f'"{reason}". {mention} ahora está en la lista blanca.',
                color=self.bot.main_color,
            )
        else:
            embed = discord.Embed(
                title="Éxito",
                color=self.bot.main_color,
                description=f"{mention} is now whitelisted.",
            )

        return await ctx.send(embed=embed)

    @commands.command(usage="[usuario] [duración] [razón]")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def block(self, ctx, user: Optional[User] = None, *, after: UserFriendlyTime = None):
        """
        Bloquear a un usuario para que no use RequiemSupport.
        Puede elegir establecer una hora en la que el usuario se desbloqueará automáticamente.
        Deje `usuario` en blanco cuando este comando se use dentro de un
        canal de ticket para bloquear el destinatario actual.
        `usuario` puede ser la ID del usuario, una mención o un nombre.
        `duración` puede ser un simple texto de tiempo. Ver tambíen `{prefix}help close` para ejemplos.
        """

        if user is None:
            thread = ctx.thread
            if thread:
                user = thread.recipient
            elif after is None:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="user"))
            else:
                raise commands.BadArgument(f'Usuario "{after.arg}" no encontrado.')

        mention = getattr(user, "mention", f"`{user.id}`")

        if str(user.id) in self.bot.blocked_whitelisted_users:
            embed = discord.Embed(
                title="Error",
                description=f"No se puede bloquear a {mention}, el usuario está en la lista blanca.",
                color=self.bot.error_color,
            )
            return await ctx.send(embed=embed)

        reason = f"by {escape_markdown(ctx.author.name)}#{ctx.author.discriminator}"

        if after is not None:
            if "%" in reason:
                raise commands.BadArgument('La razón contiene carácter ilegal "%".')
            if after.arg:
                reason += f" for `{after.arg}`"
            if after.dt > after.now:
                reason += f" until {after.dt.isoformat()}"

        reason += "."

        msg = self.bot.blocked_users.get(str(user.id))
        if msg is None:
            msg = ""

        if str(user.id) in self.bot.blocked_users and msg:
            old_reason = msg.strip().rstrip(".")
            embed = discord.Embed(
                title="Éxito",
                description=f"{mention} fue previamente bloqueado por: {old_reason}.\n"
                f"{mention} ahora está bloqueado por: {reason}",
                color=self.bot.main_color,
            )
        else:
            embed = discord.Embed(
                title="Éxito",
                color=self.bot.main_color,
                description=f"{mention} ahora está bloqueado por: {reason}",
            )
        self.bot.blocked_users[str(user.id)] = reason
        await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def unblock(self, ctx, *, user: User = None):
        """
        Desbloquear a un usuario para que no use RequiemSupport.
        Deje `Usuario` en blanco cuando este comando se utilice dentro de un
        canal de ticket para desbloquear el destinatario actual.
        `usuario` puede ser el ID de usuario, una mención o un nombre.
        """

        if user is None:
            thread = ctx.thread
            if thread:
                user = thread.recipient
            else:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="user"))

        mention = getattr(user, "mention", f"`{user.id}`")
        name = getattr(user, "name", f"`{user.id}`")

        if str(user.id) in self.bot.blocked_users:
            msg = self.bot.blocked_users.pop(str(user.id)) or ""
            await self.bot.config.update()

            if msg.startswith("Mensaje del sistema: "):
                # If the user is blocked internally (for example: below minimum account age)
                # Show an extended message stating the original internal message
                reason = msg[16:].strip().rstrip(".") or "Sin razón"
                embed = discord.Embed(
                    title="Éxito",
                    description=f"{mention} fue previamente bloqueado internamente {reason}.\n"
                    f"{mention} ya no está bloqueado.",
                    color=self.bot.main_color,
                )
                embed.set_footer(
                    text="Sin embargo, si el motivo del bloqueo del sistema original aún se aplica, "
                    f"{name} se bloqueará automáticamente de nuevo. "
                    f'Usa "{self.bot.prefix}blocked whitelist {user.id}" para incluir al usuario en la lista blanca.'
                )
            else:
                embed = discord.Embed(
                    title="Éxito",
                    color=self.bot.main_color,
                    description=f"{mention} ya no está bloqueado.",
                )
        else:
            embed = discord.Embed(
                title="Error", description=f"{mention} no está bloqueado.", color=self.bot.error_color
            )

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def delete(self, ctx, message_id: int = None):
        """
        Elimine un mensaje que se envió mediante el comando de respuesta o una nota.
        Elimina el mensaje anterior, a menos que se proporcione un ID de mensaje,
        que en ese caso, elimina el mensaje con ese ID de mensaje.
        Las notas solo se pueden eliminar cuando se proporciona un ID de nota.
        """
        thread = ctx.thread

        try:
            await thread.delete_message(message_id, note=True)
        except ValueError as e:
            logger.warning("Failed to delete message: %s.", e)
            return await ctx.send(
                embed=discord.Embed(
                    title="Fallido",
                    description="No se puede encontrar un mensaje para eliminar.",
                    color=self.bot.error_color,
                )
            )

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def repair(self, ctx):
        """
        Repara un ticket roto por Discord.
        """
        sent_emoji, blocked_emoji = await self.bot.retrieve_emoji()

        if ctx.thread:
            user_id = match_user_id(ctx.channel.topic)
            if user_id == -1:
                logger.info("Setting current channel's topic to User ID.")
                await ctx.channel.edit(topic=f"User ID: {ctx.thread.id}")
            return await self.bot.add_reaction(ctx.message, sent_emoji)

        logger.info("Intentando arreglar ticket roto %s.", ctx.channel.name)

        # Search cache for channel
        user_id, thread = next(
            ((k, v) for k, v in self.bot.threads.cache.items() if v.channel == ctx.channel),
            (-1, None),
        )
        if thread is not None:
            logger.debug("Ticket encontrado con ID templado.")
            await ctx.channel.edit(reason="Reparar ticket de RequiemSupport roto", topic=f"ID de Usuario: {user_id}")
            return await self.bot.add_reaction(ctx.message, sent_emoji)

        # find genesis message to retrieve User ID
        async for message in ctx.channel.history(limit=10, oldest_first=True):
            if (
                message.author == self.bot.user
                and message.embeds
                and message.embeds[0].color
                and message.embeds[0].color.value == self.bot.main_color
                and message.embeds[0].footer.text
            ):
                user_id = match_user_id(message.embeds[0].footer.text)
                if user_id != -1:
                    recipient = self.bot.get_user(user_id)
                    if recipient is None:
                        self.bot.threads.cache[user_id] = thread = Thread(
                            self.bot.threads, user_id, ctx.channel
                        )
                    else:
                        self.bot.threads.cache[user_id] = thread = Thread(
                            self.bot.threads, recipient, ctx.channel
                        )
                    thread.ready = True
                    logger.info(
                        "Establecer el tema del canal actual a el ID de usuario y crear un nuevo ticket."
                    )
                    await ctx.channel.edit(
                        reason="Reparar ticket de RequiemSupport roto", topic=f"ID de Usuario: {user_id}"
                    )
                    return await self.bot.add_reaction(ctx.message, sent_emoji)

        else:
            logger.warning("No genesis message found.")

        # match username from channel name
        # username-1234, username-1234_1, username-1234_2
        m = re.match(r"^(.+)-(\d{4})(?:_\d+)?$", ctx.channel.name)
        if m is not None:
            users = set(
                filter(
                    lambda member: member.name == m.group(1)
                    and member.discriminator == m.group(2),
                    ctx.guild.members,
                )
            )
            if len(users) == 1:
                user = users.pop()
                name = format_channel_name(
                    user, self.bot.modmail_guild, exclude_channel=ctx.channel
                )
                recipient = self.bot.get_user(user.id)
                if user.id in self.bot.threads.cache:
                    thread = self.bot.threads.cache[user.id]
                    if thread.channel:
                        embed = discord.Embed(
                            title="Eliminar Canal",
                            description="Este canal de ticket ya no está en uso."
                            f"Todos los mensajes se dirigirán a {ctx.channel.mention}.",
                            color=self.bot.error_color,
                        )
                        embed.set_footer(
                            text='Elimine manualmente este canal, no utilice "{prefix}close".'
                        )
                        try:
                            await thread.channel.send(embed=embed)
                        except discord.HTTPException:
                            pass
                if recipient is None:
                    self.bot.threads.cache[user.id] = thread = Thread(
                        self.bot.threads, user_id, ctx.channel
                    )
                else:
                    self.bot.threads.cache[user.id] = thread = Thread(
                        self.bot.threads, recipient, ctx.channel
                    )
                thread.ready = True
                logger.info("Estableciendo el tema del canal actual a la ID de usuario y creando un nuevo ticket.")
                await ctx.channel.edit(
                    reason="Reparar ticket de RequiemSupport roto", name=name, topic=f"ID de Usuario: {user.id}"
                )
                return await self.bot.add_reaction(ctx.message, sent_emoji)

            elif len(users) >= 2:
                logger.info("Múltiples usuarios con el mismo nombre y discriminador.")
        return await self.bot.add_reaction(ctx.message, blocked_emoji)
                                
    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def enable(self, ctx):
        """
        Vuelve a habilitar las funciones de DM de RequiemSupport.
        Deshace el comando `{prefix}disable`, todos los tickets se transmitirán después de ejecutar este comando.
        """
        embed = discord.Embed(
            title="Éxito",
            description="RequiemSupport ahora aceptará todos los mensajes DM.",
            color=self.bot.main_color,
        )

        if self.bot.config["dm_disabled"] != 0:
            self.bot.config["dm_disabled"] = 0
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def disable(self, ctx):
        """
        Deshabilite las funciones de subprocesos de RequiemSupport parciales o totales.
        Para evitar que se creen todos los tickets nuevos, haga `{prefix}disable new`.
        Para detener todos los tickets existentes de RequiemSupport, haga `{prefix}disable all`.
        Para comprobar si la función DM para RequiemSupport está habilitada, haga `{prefix}isenable`.
        """
        await ctx.send_help(ctx.command)

    @disable.command(name="new")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def disable_new(self, ctx):
        """
        Deje de aceptar nuevos tickets de RequiemSupport.
        No se pueden crear nuevos tickets a través de DM.
        """
        embed = discord.Embed(
            title="Éxito",
            description="RequiemSupport no creará nuevos tickets.",
            color=self.bot.main_color,
        )
        if self.bot.config["dm_disabled"] < 1:
            self.bot.config["dm_disabled"] = 1
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @disable.command(name="all")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def disable_all(self, ctx):
        """
        Desactiva todas las funciones de DM de RequiemSupport.
        No se pueden crear nuevos tickets a través de DM ni se retransmitirán más mensajes DM.
        """
        embed = discord.Embed(
            title="Éxito",
            description="RequiemSupport no aceptará ningún mensaje DM.",
            color=self.bot.main_color,
        )

        if self.bot.config["dm_disabled"] != 2:
            self.bot.config["dm_disabled"] = 2
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def isenable(self, ctx):
        """
        Compruebe si las funcionalidades DM de RequiemSupport están habilitadas.
        """

        if self.bot.config["dm_disabled"] == 1:
            embed = discord.Embed(
                title="Nuevos tickets deshabilitados",
                description="RequiemSupport no está creando nuevos tickets.",
                color=self.bot.error_color,
            )
        elif self.bot.config["dm_disabled"] == 2:
            embed = discord.Embed(
                title="Todo DM Desactivado",
                description="RequiemSupport no acepta mensajes DM para tickets nuevos y existentes.",
                color=self.bot.error_color,
            )
        else:
            embed = discord.Embed(
                title="Habilitado",
                description="RequiemSupport ahora acepta todos los mensajes DM.",
                color=self.bot.main_color,
            )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Soporte(bot))
