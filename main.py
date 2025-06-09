import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio
from datetime import datetime
import wavelink

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord_bot')

# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents)

# Music player class
class MusicPlayer:
    def __init__(self):
        self.queue = []
        self.current = None
        self.volume = 100

# Store music players for each guild
music_players = {}

# Warning system storage
warnings = {}

# Auto-role storage
auto_roles = {}

# Bad word filter storage
banned_words = {}

# Ticket system storage
ticket_channels = {}
ticket_counters = {}

# Logging system storage
log_channels = {}

# Event: Bot is ready
@bot.event
async def on_ready():
    logger.info(f'Bot is ready! Logged in as {bot.user.name} ({bot.user.id})')
    try:
        # Initialize wavelink nodes
        nodes = [
            wavelink.Node(
                uri='http://localhost:2333',  # Lavalink server address
                password='youshallnotpass'    # Lavalink server password
            )
        ]
        await wavelink.NodePool.connect(client=bot, nodes=nodes)
        logger.info("Connected to Lavalink nodes")
        
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

# Event: Wavelink node ready
@bot.event
async def on_wavelink_node_ready(node: wavelink.Node):
    logger.info(f"Wavelink node '{node.identifier}' is ready!")

# Event: Track end
@bot.event
async def on_wavelink_track_end(player: wavelink.Player, track: wavelink.Track, reason):
    guild_id = player.guild.id
    if guild_id in music_players and music_players[guild_id].queue:
        next_track = music_players[guild_id].queue.pop(0)
        await player.play(next_track)
        music_players[guild_id].current = next_track

# Event: Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found. Use !help to see available commands.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    else:
        logger.error(f"An error occurred: {error}")
        await ctx.send("An error occurred while processing your command.")

# Event: Member join
@bot.event
async def on_member_join(member):
    """Assign auto-roles when a member joins"""
    guild_id = member.guild.id
    if guild_id in auto_roles and auto_roles[guild_id]:
        try:
            roles_to_add = []
            for role in auto_roles[guild_id]:
                if role not in member.roles:
                    roles_to_add.append(role)
            
            if roles_to_add:
                await member.add_roles(*roles_to_add)
                logger.info(f"Assigned auto-roles to {member.name} ({member.id})")
        except Exception as e:
            logger.error(f"Error assigning auto-roles to {member.name}: {e}")

# Event: Message handling
@bot.event
async def on_message(message):
    """Check messages for banned words"""
    # Ignore messages from bots
    if message.author.bot:
        return

    # Check if the message is from a guild
    if not message.guild:
        return

    guild_id = message.guild.id
    if guild_id not in banned_words:
        return

    # Get banned words and action
    banned_words_set, action = banned_words[guild_id]
    
    # Check if message contains any banned words
    message_content = message.content.lower()
    found_words = [word for word in banned_words_set if word in message_content]
    
    if found_words:
        try:
            # Delete the message
            await message.delete()
            
            # Take additional action based on setting
            if action == 'warn':
                embed = discord.Embed(
                    title="⚠️ Warning",
                    description=f"{message.author.mention}, please avoid using inappropriate language.",
                    color=discord.Color.yellow()
                )
                embed.add_field(name="Banned Words Used", value=", ".join(found_words))
                await message.channel.send(embed=embed, delete_after=10)
                
            elif action == 'timeout':
                try:
                    # Timeout the user for 5 minutes
                    await message.author.timeout(datetime.timedelta(minutes=5), reason="Using banned words")
                    embed = discord.Embed(
                        title="⏰ User Timed Out",
                        description=f"{message.author.mention} has been timed out for 5 minutes for using inappropriate language.",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="Banned Words Used", value=", ".join(found_words))
                    await message.channel.send(embed=embed, delete_after=10)
                except discord.Forbidden:
                    await message.channel.send("I don't have permission to timeout users.")
            
            # Log the incident
            logger.info(f"Banned word used by {message.author} ({message.author.id}) in {message.guild.name}: {found_words}")
            
        except discord.Forbidden:
            await message.channel.send("I don't have permission to delete messages.")
        except Exception as e:
            logger.error(f"Error handling banned word: {e}")

    # Process commands after checking for banned words
    await bot.process_commands(message)

# Command: Ping
@bot.command(name='ping')
async def ping(ctx):
    """Check the bot's latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! Latency: {latency}ms')

# Command: Server Info
@bot.command(name='serverinfo')
async def server_info(ctx):
    """Display information about the server"""
    guild = ctx.guild
    embed = discord.Embed(title=f"{guild.name} Info", color=discord.Color.blue())
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Created On", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Member Count", value=guild.member_count, inline=True)
    embed.add_field(name="Channel Count", value=len(guild.channels), inline=True)
    embed.add_field(name="Role Count", value=len(guild.roles), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await ctx.send(embed=embed)

# Command: User Info
@bot.command(name='userinfo')
async def user_info(ctx, member: discord.Member = None):
    """Display information about a user"""
    member = member or ctx.author
    roles = [role.mention for role in member.roles[1:]]
    roles_str = ", ".join(roles) if roles else "No roles"
    
    embed = discord.Embed(title=f"User Info - {member.name}", color=member.color)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Roles", value=roles_str, inline=False)
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)

# Command: Clear Messages
@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    """Clear a specified number of messages"""
    if amount <= 0:
        await ctx.send("Please specify a positive number of messages to delete.")
        return
    
    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Deleted {len(deleted)-1} messages.", delete_after=5)
    except Exception as e:
        logger.error(f"Error clearing messages: {e}")
        await ctx.send("An error occurred while trying to clear messages.")

# Command: Poll
@bot.command(name='poll')
async def poll(ctx, question: str, *options):
    """Create a poll with reactions"""
    if len(options) > 10:
        await ctx.send("You can only have up to 10 options!")
        return

    emoji_numbers = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    description = []
    for idx, option in enumerate(options):
        description.append(f'{emoji_numbers[idx]} {option}')
    
    embed = discord.Embed(title=question, description='\n'.join(description), color=discord.Color.blue())
    poll_message = await ctx.send(embed=embed)
    
    for idx in range(len(options)):
        await poll_message.add_reaction(emoji_numbers[idx])

# Moderation Commands
@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Kick a member from the server"""
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="Member Kicked",
            description=f"{member.mention} has been kicked from the server.",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
        logger.info(f"{member} was kicked by {ctx.author} for reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to kick this member.")
    except Exception as e:
        logger.error(f"Error kicking member: {e}")
        await ctx.send("An error occurred while trying to kick the member.")

@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Ban a member from the server"""
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="Member Banned",
            description=f"{member.mention} has been banned from the server.",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
        logger.info(f"{member} was banned by {ctx.author} for reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to ban this member.")
    except Exception as e:
        logger.error(f"Error banning member: {e}")
        await ctx.send("An error occurred while trying to ban the member.")

@bot.command(name='unban')
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    """Unban a user by their ID"""
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        embed = discord.Embed(
            title="Member Unbanned",
            description=f"{user.mention} has been unbanned from the server.",
            color=discord.Color.green()
        )
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
        logger.info(f"{user} was unbanned by {ctx.author}")
    except discord.NotFound:
        await ctx.send("User not found.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to unban this user.")
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        await ctx.send("An error occurred while trying to unban the user.")

@bot.command(name='timeout')
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason: str = "No reason provided"):
    """Timeout a member for specified minutes"""
    if minutes <= 0:
        await ctx.send("Please specify a positive number of minutes.")
        return
    
    try:
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        embed = discord.Embed(
            title="Member Timed Out",
            description=f"{member.mention} has been timed out for {minutes} minutes.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
        logger.info(f"{member} was timed out by {ctx.author} for {minutes} minutes. Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to timeout this member.")
    except Exception as e:
        logger.error(f"Error timing out member: {e}")
        await ctx.send("An error occurred while trying to timeout the member.")

@bot.command(name='mute')
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Mute a member by adding the Muted role"""
    try:
        # Get or create Muted role
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not muted_role:
            muted_role = await ctx.guild.create_role(name="Muted")
            # Set permissions for the muted role
            for channel in ctx.guild.channels:
                await channel.set_permissions(muted_role, speak=False, send_messages=False)
        
        await member.add_roles(muted_role)
        embed = discord.Embed(
            title="Member Muted",
            description=f"{member.mention} has been muted.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
        logger.info(f"{member} was muted by {ctx.author} for reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to mute this member.")
    except Exception as e:
        logger.error(f"Error muting member: {e}")
        await ctx.send("An error occurred while trying to mute the member.")

@bot.command(name='unmute')
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    """Unmute a member by removing the Muted role"""
    try:
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if muted_role in member.roles:
            await member.remove_roles(muted_role)
            embed = discord.Embed(
                title="Member Unmuted",
                description=f"{member.mention} has been unmuted.",
                color=discord.Color.green()
            )
            embed.add_field(name="Moderator", value=ctx.author.mention)
            await ctx.send(embed=embed)
            logger.info(f"{member} was unmuted by {ctx.author}")
        else:
            await ctx.send("This member is not muted.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to unmute this member.")
    except Exception as e:
        logger.error(f"Error unmuting member: {e}")
        await ctx.send("An error occurred while trying to unmute the member.")

# Add error handling for moderation commands
@kick.error
@ban.error
@unban.error
@timeout.error
@mute.error
@unmute.error
async def moderation_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide all required arguments.")
    else:
        logger.error(f"Moderation command error: {error}")
        await ctx.send("An error occurred while processing the command.")

# Music Commands
@bot.command(name='play')
async def play(ctx, *, query: str):
    """Play a song from YouTube"""
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel to use this command!")
        return

    if not ctx.voice_client:
        vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
    else:
        vc: wavelink.Player = ctx.voice_client

    # Initialize music player for the guild if it doesn't exist
    if ctx.guild.id not in music_players:
        music_players[ctx.guild.id] = MusicPlayer()

    # Search for the track
    search = await wavelink.NodePool.get_node().get_tracks(query)
    if not search:
        await ctx.send("No tracks found!")
        return

    track = search[0]
    
    if vc.is_playing():
        music_players[ctx.guild.id].queue.append(track)
        await ctx.send(f"Added to queue: {track.title}")
    else:
        await vc.play(track)
        music_players[ctx.guild.id].current = track
        await ctx.send(f"Now playing: {track.title}")

@bot.command(name='stop')
async def stop(ctx):
    """Stop the current playback and clear the queue"""
    if not ctx.voice_client:
        await ctx.send("I'm not playing anything!")
        return

    vc: wavelink.Player = ctx.voice_client
    await vc.stop()
    if ctx.guild.id in music_players:
        music_players[ctx.guild.id].queue.clear()
        music_players[ctx.guild.id].current = None
    await ctx.send("Stopped playback and cleared queue")

@bot.command(name='pause')
async def pause(ctx):
    """Pause the current playback"""
    if not ctx.voice_client:
        await ctx.send("I'm not playing anything!")
        return

    vc: wavelink.Player = ctx.voice_client
    if vc.is_paused():
        await ctx.send("Already paused!")
        return

    await vc.pause()
    await ctx.send("Paused playback")

@bot.command(name='resume')
async def resume(ctx):
    """Resume the current playback"""
    if not ctx.voice_client:
        await ctx.send("I'm not playing anything!")
        return

    vc: wavelink.Player = ctx.voice_client
    if not vc.is_paused():
        await ctx.send("Not paused!")
        return

    await vc.resume()
    await ctx.send("Resumed playback")

@bot.command(name='skip')
async def skip(ctx):
    """Skip the current song"""
    if not ctx.voice_client:
        await ctx.send("I'm not playing anything!")
        return

    vc: wavelink.Player = ctx.voice_client
    await vc.stop()
    await ctx.send("Skipped current song")

@bot.command(name='queue')
async def queue(ctx):
    """Show the current queue"""
    if ctx.guild.id not in music_players:
        await ctx.send("No queue exists!")
        return

    player = music_players[ctx.guild.id]
    if not player.current and not player.queue:
        await ctx.send("Queue is empty!")
        return

    embed = discord.Embed(title="Music Queue", color=discord.Color.blue())
    
    if player.current:
        embed.add_field(name="Now Playing", value=player.current.title, inline=False)
    
    if player.queue:
        queue_list = "\n".join([f"{i+1}. {track.title}" for i, track in enumerate(player.queue)])
        embed.add_field(name="Up Next", value=queue_list, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='volume')
async def volume(ctx, volume: int):
    """Set the volume (0-100)"""
    if not ctx.voice_client:
        await ctx.send("I'm not playing anything!")
        return

    if not 0 <= volume <= 100:
        await ctx.send("Volume must be between 0 and 100!")
        return

    vc: wavelink.Player = ctx.voice_client
    await vc.set_volume(volume)
    if ctx.guild.id in music_players:
        music_players[ctx.guild.id].volume = volume
    await ctx.send(f"Volume set to {volume}%")

# Warning system commands
@bot.command(name='warn')
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Warn a member"""
    if member.id not in warnings:
        warnings[member.id] = []
    
    warnings[member.id].append({
        'reason': reason,
        'moderator': ctx.author.id,
        'timestamp': datetime.utcnow()
    })
    
    embed = discord.Embed(
        title="Member Warned",
        description=f"{member.mention} has been warned.",
        color=discord.Color.yellow()
    )
    embed.add_field(name="Reason", value=reason)
    embed.add_field(name="Moderator", value=ctx.author.mention)
    embed.add_field(name="Total Warnings", value=len(warnings[member.id]))
    await ctx.send(embed=embed)
    
    # DM the warned user
    try:
        dm_embed = discord.Embed(
            title=f"You have been warned in {ctx.guild.name}",
            description=f"Reason: {reason}",
            color=discord.Color.yellow()
        )
        await member.send(embed=dm_embed)
    except:
        pass  # If DM fails, just continue

@bot.command(name='warnings')
@commands.has_permissions(manage_messages=True)
async def view_warnings(ctx, member: discord.Member):
    """View warnings for a member"""
    if member.id not in warnings or not warnings[member.id]:
        await ctx.send(f"{member.mention} has no warnings.")
        return
    
    embed = discord.Embed(
        title=f"Warnings for {member.name}",
        color=discord.Color.yellow()
    )
    
    for i, warning in enumerate(warnings[member.id], 1):
        moderator = ctx.guild.get_member(warning['moderator'])
        moderator_name = moderator.name if moderator else "Unknown"
        embed.add_field(
            name=f"Warning #{i}",
            value=f"Reason: {warning['reason']}\nModerator: {moderator_name}\nDate: {warning['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='clearwarnings')
@commands.has_permissions(administrator=True)
async def clear_warnings(ctx, member: discord.Member):
    """Clear all warnings for a member"""
    if member.id in warnings:
        del warnings[member.id]
        await ctx.send(f"Cleared all warnings for {member.mention}")
    else:
        await ctx.send(f"{member.mention} has no warnings to clear.")

@bot.command(name='slowmode')
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    """Set slowmode for the current channel"""
    if seconds < 0:
        await ctx.send("Slowmode cannot be negative!")
        return
    
    await ctx.channel.edit(slowmode_delay=seconds)
    if seconds == 0:
        await ctx.send("Slowmode has been disabled.")
    else:
        await ctx.send(f"Slowmode set to {seconds} seconds.")

@bot.command(name='lock')
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    """Lock the current channel"""
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Channel locked.")

@bot.command(name='unlock')
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Unlock the current channel"""
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Channel unlocked.")

@bot.command(name='role')
@commands.has_permissions(manage_roles=True)
async def role(ctx, member: discord.Member, role: discord.Role):
    """Add or remove a role from a member"""
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"Removed {role.name} from {member.mention}")
    else:
        await member.add_roles(role)
        await ctx.send(f"Added {role.name} to {member.mention}")

@bot.command(name='purge')
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int, member: discord.Member = None):
    """Delete a specified number of messages, optionally from a specific member"""
    if amount <= 0:
        await ctx.send("Please specify a positive number of messages to delete.")
        return
    
    def check(msg):
        return member is None or msg.author == member
    
    try:
        deleted = await ctx.channel.purge(limit=amount + 1, check=check)
        await ctx.send(f"Deleted {len(deleted)-1} messages.", delete_after=5)
    except Exception as e:
        logger.error(f"Error purging messages: {e}")
        await ctx.send("An error occurred while trying to purge messages.")

@bot.command(name='tempban')
@commands.has_permissions(ban_members=True)
async def tempban(ctx, member: discord.Member, duration: int, *, reason: str = "No reason provided"):
    """Temporarily ban a member for specified minutes"""
    if duration <= 0:
        await ctx.send("Please specify a positive duration in minutes.")
        return
    
    try:
        await member.ban(reason=f"{reason} (Temp ban: {duration} minutes)")
        embed = discord.Embed(
            title="Member Temporarily Banned",
            description=f"{member.mention} has been banned for {duration} minutes.",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
        
        # Unban after duration
        await asyncio.sleep(duration * 60)
        await ctx.guild.unban(member)
        await ctx.send(f"{member.mention} has been unbanned after {duration} minutes.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to ban this member.")
    except Exception as e:
        logger.error(f"Error in tempban: {e}")
        await ctx.send("An error occurred while trying to tempban the member.")

@bot.command(name='nickname')
@commands.has_permissions(manage_nicknames=True)
async def nickname(ctx, member: discord.Member, *, new_nickname: str = None):
    """Change a member's nickname"""
    try:
        await member.edit(nick=new_nickname)
        if new_nickname:
            await ctx.send(f"Changed {member.mention}'s nickname to {new_nickname}")
        else:
            await ctx.send(f"Reset {member.mention}'s nickname")
    except discord.Forbidden:
        await ctx.send("I don't have permission to change this member's nickname.")
    except Exception as e:
        logger.error(f"Error changing nickname: {e}")
        await ctx.send("An error occurred while trying to change the nickname.")

@bot.command(name='muteall')
@commands.has_permissions(mute_members=True)
async def muteall(ctx):
    """Mute all members in the current voice channel"""
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel to use this command!")
        return
    
    channel = ctx.author.voice.channel
    muted_count = 0
    
    for member in channel.members:
        if not member.voice.mute and not member.bot:
            try:
                await member.edit(mute=True)
                muted_count += 1
            except:
                continue
    
    await ctx.send(f"Muted {muted_count} members in the voice channel.")

@bot.command(name='unmuteall')
@commands.has_permissions(mute_members=True)
async def unmuteall(ctx):
    """Unmute all members in the current voice channel"""
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel to use this command!")
        return
    
    channel = ctx.author.voice.channel
    unmuted_count = 0
    
    for member in channel.members:
        if member.voice.mute and not member.bot:
            try:
                await member.edit(mute=False)
                unmuted_count += 1
            except:
                continue
    
    await ctx.send(f"Unmuted {unmuted_count} members in the voice channel.")

# Add error handling for new moderation commands
@warn.error
@warnings.error
@clearwarnings.error
@slowmode.error
@lock.error
@unlock.error
@role.error
@purge.error
@tempban.error
@nickname.error
@muteall.error
@unmuteall.error
async def moderation_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide all required arguments.")
    else:
        logger.error(f"Moderation command error: {error}")
        await ctx.send("An error occurred while processing the command.")

@bot.command(name='banned')
@commands.has_permissions(ban_members=True)
async def view_banned(ctx):
    """View all banned users in the server"""
    try:
        bans = await ctx.guild.bans()
        if not bans:
            await ctx.send("No users are currently banned.")
            return

        embed = discord.Embed(
            title="Banned Users",
            color=discord.Color.red()
        )
        
        # Discord has a limit of 25 fields per embed
        for i, ban_entry in enumerate(bans[:25], 1):
            user = ban_entry.user
            reason = ban_entry.reason or "No reason provided"
            embed.add_field(
                name=f"{i}. {user.name}#{user.discriminator}",
                value=f"ID: {user.id}\nReason: {reason}",
                inline=False
            )
        
        if len(bans) > 25:
            embed.set_footer(text=f"Showing 25 of {len(bans)} banned users")
        
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("I don't have permission to view the ban list.")
    except Exception as e:
        logger.error(f"Error viewing banned users: {e}")
        await ctx.send("An error occurred while trying to view banned users.")

@bot.command(name='isbanned')
@commands.has_permissions(ban_members=True)
async def check_ban(ctx, user_id: int):
    """Check if a user is banned by their ID"""
    try:
        user = await bot.fetch_user(user_id)
        ban_entry = await ctx.guild.fetch_ban(user)
        
        embed = discord.Embed(
            title="User is Banned",
            color=discord.Color.red()
        )
        embed.add_field(name="User", value=f"{user.name}#{user.discriminator}", inline=True)
        embed.add_field(name="User ID", value=user.id, inline=True)
        embed.add_field(name="Ban Reason", value=ban_entry.reason or "No reason provided", inline=False)
        
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
            
        await ctx.send(embed=embed)
    except discord.NotFound:
        await ctx.send(f"User with ID {user_id} is not banned.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to check ban status.")
    except Exception as e:
        logger.error(f"Error checking ban status: {e}")
        await ctx.send("An error occurred while checking ban status.")

@bot.command(name='baninfo')
@commands.has_permissions(ban_members=True)
async def ban_info(ctx, user: discord.User):
    """Get detailed information about a user's ban"""
    try:
        ban_entry = await ctx.guild.fetch_ban(user)
        
        embed = discord.Embed(
            title="Ban Information",
            color=discord.Color.red()
        )
        
        # User Information
        embed.add_field(name="User", value=f"{user.name}#{user.discriminator}", inline=True)
        embed.add_field(name="User ID", value=user.id, inline=True)
        embed.add_field(name="Account Created", value=user.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        
        # Ban Information
        embed.add_field(name="Ban Reason", value=ban_entry.reason or "No reason provided", inline=False)
        
        # Try to get the user's avatar
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        # Add a footer with the command used
        embed.set_footer(text=f"Requested by {ctx.author.name}")
        
        await ctx.send(embed=embed)
    except discord.NotFound:
        await ctx.send(f"{user.name} is not banned in this server.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to view ban information.")
    except Exception as e:
        logger.error(f"Error getting ban information: {e}")
        await ctx.send("An error occurred while getting ban information.")

# Add error handling for new ban commands
@banned.error
@isbanned.error
@baninfo.error
async def ban_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide all required arguments.")
    else:
        logger.error(f"Ban command error: {error}")
        await ctx.send("An error occurred while processing the command.")

# Server Analysis Commands
@bot.command(name='serverstats')
async def server_stats(ctx):
    """Get detailed AI-powered analysis of the server"""
    guild = ctx.guild
    
    # Calculate various statistics
    total_members = guild.member_count
    online_members = len([m for m in guild.members if m.status != discord.Status.offline])
    bot_count = len([m for m in guild.members if m.bot])
    human_count = total_members - bot_count
    
    # Channel statistics
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    
    # Role statistics
    role_count = len(guild.roles)
    
    # Create main embed
    embed = discord.Embed(
        title=f"🤖 AI Analysis of {guild.name}",
        color=discord.Color.blue()
    )
    
    # Server Overview
    embed.add_field(
        name="📊 Server Overview",
        value=f"• Created: {guild.created_at.strftime('%Y-%m-%d')}\n"
              f"• Owner: {guild.owner.mention}\n"
              f"• Server ID: {guild.id}\n"
              f"• Boost Level: {guild.premium_tier}",
        inline=False
    )
    
    # Member Analysis
    member_activity = "🟢 Active" if online_members/total_members > 0.3 else "🔴 Less Active"
    embed.add_field(
        name="👥 Member Analysis",
        value=f"• Total Members: {total_members}\n"
              f"• Online Members: {online_members}\n"
              f"• Humans: {human_count}\n"
              f"• Bots: {bot_count}\n"
              f"• Activity Status: {member_activity}",
        inline=False
    )
    
    # Channel Analysis
    channel_ratio = "📝 Text-Heavy" if text_channels > voice_channels else "🎤 Voice-Heavy"
    embed.add_field(
        name="📚 Channel Analysis",
        value=f"• Text Channels: {text_channels}\n"
              f"• Voice Channels: {voice_channels}\n"
              f"• Categories: {categories}\n"
              f"• Server Type: {channel_ratio}",
        inline=False
    )
    
    # Role Analysis
    embed.add_field(
        name="🎭 Role Analysis",
        value=f"• Total Roles: {role_count}\n"
              f"• Role Complexity: {'High' if role_count > 10 else 'Low'}",
        inline=False
    )
    
    # Server Features
    features = []
    if guild.premium_tier > 0:
        features.append("✨ Boosted")
    if guild.verification_level != discord.VerificationLevel.none:
        features.append("🔒 Verified")
    if guild.explicit_content_filter != discord.ContentFilter.disabled:
        features.append("🛡️ Content Filtered")
    
    if features:
        embed.add_field(
            name="🌟 Server Features",
            value="\n".join(f"• {feature}" for feature in features),
            inline=False
        )
    
    # Server Health
    health_status = "✅ Healthy" if (online_members/total_members > 0.2 and text_channels > 0) else "⚠️ Needs Attention"
    embed.add_field(
        name="💊 Server Health",
        value=f"• Status: {health_status}\n"
              f"• Member Retention: {'Good' if online_members/total_members > 0.3 else 'Could be improved'}\n"
              f"• Channel Activity: {'Balanced' if abs(text_channels - voice_channels) <= 2 else 'Unbalanced'}",
        inline=False
    )
    
    # Recommendations
    recommendations = []
    if online_members/total_members < 0.2:
        recommendations.append("• Consider hosting more events to increase activity")
    if text_channels == 0:
        recommendations.append("• Add some text channels for better communication")
    if role_count < 3:
        recommendations.append("• Consider adding more roles for better organization")
    
    if recommendations:
        embed.add_field(
            name="💡 AI Recommendations",
            value="\n".join(recommendations),
            inline=False
        )
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.set_footer(text="Analysis generated by AI")
    await ctx.send(embed=embed)

@bot.command(name='memberstats')
async def member_stats(ctx, member: discord.Member = None):
    """Get AI-powered analysis of a member or yourself"""
    member = member or ctx.author
    
    # Calculate member statistics
    joined_days = (datetime.utcnow() - member.joined_at).days
    account_age = (datetime.utcnow() - member.created_at).days
    
    # Create embed
    embed = discord.Embed(
        title=f"🤖 AI Analysis of {member.name}",
        color=member.color
    )
    
    # Basic Information
    embed.add_field(
        name="👤 Basic Information",
        value=f"• Name: {member.name}#{member.discriminator}\n"
              f"• ID: {member.id}\n"
              f"• Joined: {member.joined_at.strftime('%Y-%m-%d')}\n"
              f"• Account Created: {member.created_at.strftime('%Y-%m-%d')}",
        inline=False
    )
    
    # Member Analysis
    member_type = "👑 Server Owner" if member == ctx.guild.owner else "🤖 Bot" if member.bot else "👥 Regular Member"
    embed.add_field(
        name="📊 Member Analysis",
        value=f"• Type: {member_type}\n"
              f"• Server Tenure: {joined_days} days\n"
              f"• Account Age: {account_age} days\n"
              f"• Top Role: {member.top_role.mention}",
        inline=False
    )
    
    # Role Analysis
    roles = [role.mention for role in member.roles[1:]]  # Exclude @everyone
    role_count = len(roles)
    role_complexity = "High" if role_count > 3 else "Low"
    
    embed.add_field(
        name="🎭 Role Analysis",
        value=f"• Role Count: {role_count}\n"
              f"• Role Complexity: {role_complexity}\n"
              f"• Roles: {', '.join(roles) if roles else 'No roles'}",
        inline=False
    )
    
    # Activity Analysis
    status = str(member.status).title()
    activity_status = "🟢 Active" if status != "Offline" else "🔴 Inactive"
    
    embed.add_field(
        name="📈 Activity Analysis",
        value=f"• Current Status: {status}\n"
              f"• Activity Level: {activity_status}\n"
              f"• Member Since: {joined_days} days ago",
        inline=False
    )
    
    # Member Health
    health_status = "✅ Healthy" if (account_age > 30 and role_count > 0) else "⚠️ New Account"
    embed.add_field(
        name="💊 Member Health",
        value=f"• Status: {health_status}\n"
              f"• Account Security: {'Good' if account_age > 30 else 'New'}\n"
              f"• Role Integration: {'Good' if role_count > 0 else 'None'}",
        inline=False
    )
    
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    
    embed.set_footer(text="Analysis generated by AI")
    await ctx.send(embed=embed)

@bot.command(name='channelstats')
async def channel_stats(ctx, channel: discord.TextChannel = None):
    """Get AI-powered analysis of a channel or current channel"""
    channel = channel or ctx.channel
    
    # Calculate channel statistics
    channel_age = (datetime.utcnow() - channel.created_at).days
    
    # Create embed
    embed = discord.Embed(
        title=f"🤖 AI Analysis of #{channel.name}",
        color=discord.Color.blue()
    )
    
    # Channel Information
    embed.add_field(
        name="📝 Channel Information",
        value=f"• Name: #{channel.name}\n"
              f"• ID: {channel.id}\n"
              f"• Created: {channel.created_at.strftime('%Y-%m-%d')}\n"
              f"• Category: {channel.category.name if channel.category else 'None'}",
        inline=False
    )
    
    # Channel Analysis
    channel_type = "🔒 Private" if channel.permissions_for(ctx.guild.default_role).read_messages is False else "🌐 Public"
    embed.add_field(
        name="📊 Channel Analysis",
        value=f"• Type: {channel_type}\n"
              f"• Age: {channel_age} days\n"
              f"• Position: {channel.position}\n"
              f"• Slowmode: {channel.slowmode_delay}s",
        inline=False
    )
    
    # Permission Analysis
    default_perms = channel.permissions_for(ctx.guild.default_role)
    embed.add_field(
        name="🔑 Permission Analysis",
        value=f"• Read Messages: {'✅' if default_perms.read_messages else '❌'}\n"
              f"• Send Messages: {'✅' if default_perms.send_messages else '❌'}\n"
              f"• Embed Links: {'✅' if default_perms.embed_links else '❌'}\n"
              f"• Attach Files: {'✅' if default_perms.attach_files else '❌'}",
        inline=False
    )
    
    # Channel Health
    health_status = "✅ Healthy" if (channel_age > 0 and default_perms.read_messages) else "⚠️ Needs Attention"
    embed.add_field(
        name="💊 Channel Health",
        value=f"• Status: {health_status}\n"
              f"• Accessibility: {'Good' if default_perms.read_messages else 'Restricted'}\n"
              f"• Activity Potential: {'High' if default_perms.send_messages else 'Low'}",
        inline=False
    )
    
    # Recommendations
    recommendations = []
    if not default_perms.read_messages:
        recommendations.append("• Consider making the channel public for better accessibility")
    if channel.slowmode_delay == 0:
        recommendations.append("• Consider adding slowmode to prevent spam")
    if not channel.category:
        recommendations.append("• Consider adding the channel to a category for better organization")
    
    if recommendations:
        embed.add_field(
            name="💡 AI Recommendations",
            value="\n".join(recommendations),
            inline=False
        )
    
    embed.set_footer(text="Analysis generated by AI")
    await ctx.send(embed=embed)

# Add error handling for new analysis commands
@serverstats.error
@memberstats.error
@channelstats.error
async def analysis_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide all required arguments.")
    else:
        logger.error(f"Analysis command error: {error}")
        await ctx.send("An error occurred while processing the command.")

# Auto-role Commands
@bot.command(name='autorole')
@commands.has_permissions(administrator=True)
async def auto_role(ctx, action: str, role: discord.Role = None):
    """Manage auto-roles for the server
    Actions: add, remove, list, clear
    Example: !autorole add @role"""
    if action.lower() not in ['add', 'remove', 'list', 'clear']:
        await ctx.send("Invalid action! Use: add, remove, list, or clear")
        return

    guild_id = ctx.guild.id
    if guild_id not in auto_roles:
        auto_roles[guild_id] = []

    if action.lower() == 'add':
        if not role:
            await ctx.send("Please specify a role to add!")
            return
        if role in auto_roles[guild_id]:
            await ctx.send(f"{role.mention} is already an auto-role!")
            return
        auto_roles[guild_id].append(role)
        await ctx.send(f"Added {role.mention} to auto-roles!")

    elif action.lower() == 'remove':
        if not role:
            await ctx.send("Please specify a role to remove!")
            return
        if role not in auto_roles[guild_id]:
            await ctx.send(f"{role.mention} is not an auto-role!")
            return
        auto_roles[guild_id].remove(role)
        await ctx.send(f"Removed {role.mention} from auto-roles!")

    elif action.lower() == 'list':
        if not auto_roles[guild_id]:
            await ctx.send("No auto-roles set up!")
            return
        embed = discord.Embed(
            title="Auto-Roles",
            description="Roles that will be automatically assigned to new members",
            color=discord.Color.blue()
        )
        for role in auto_roles[guild_id]:
            embed.add_field(
                name=role.name,
                value=f"ID: {role.id}\nColor: {role.color}",
                inline=True
            )
        await ctx.send(embed=embed)

    elif action.lower() == 'clear':
        auto_roles[guild_id] = []
        await ctx.send("Cleared all auto-roles!")

@bot.command(name='autoroleonjoin')
@commands.has_permissions(administrator=True)
async def auto_role_on_join(ctx, role: discord.Role):
    """Set a role to be automatically assigned when members join"""
    guild_id = ctx.guild.id
    if guild_id not in auto_roles:
        auto_roles[guild_id] = []
    
    if role in auto_roles[guild_id]:
        await ctx.send(f"{role.mention} is already set to be assigned on join!")
        return
    
    auto_roles[guild_id].append(role)
    embed = discord.Embed(
        title="Auto-Role Set",
        description=f"{role.mention} will now be automatically assigned to new members",
        color=discord.Color.green()
    )
    embed.add_field(name="Role ID", value=role.id)
    embed.add_field(name="Role Color", value=str(role.color))
    await ctx.send(embed=embed)

@bot.command(name='autoroleonverify')
@commands.has_permissions(administrator=True)
async def auto_role_on_verify(ctx, role: discord.Role):
    """Set a role to be automatically assigned when members verify"""
    guild_id = ctx.guild.id
    if guild_id not in auto_roles:
        auto_roles[guild_id] = []
    
    if role in auto_roles[guild_id]:
        await ctx.send(f"{role.mention} is already set to be assigned on verify!")
        return
    
    auto_roles[guild_id].append(role)
    embed = discord.Embed(
        title="Verification Auto-Role Set",
        description=f"{role.mention} will now be automatically assigned when members verify",
        color=discord.Color.green()
    )
    embed.add_field(name="Role ID", value=role.id)
    embed.add_field(name="Role Color", value=str(role.color))
    await ctx.send(embed=embed)

@bot.command(name='autoroleinfo')
async def auto_role_info(ctx):
    """View information about auto-roles in the server"""
    guild_id = ctx.guild.id
    if guild_id not in auto_roles or not auto_roles[guild_id]:
        await ctx.send("No auto-roles are set up in this server!")
        return
    
    embed = discord.Embed(
        title="Auto-Role Information",
        color=discord.Color.blue()
    )
    
    for role in auto_roles[guild_id]:
        member_count = len(role.members)
        embed.add_field(
            name=role.name,
            value=f"ID: {role.id}\n"
                  f"Members: {member_count}\n"
                  f"Color: {role.color}\n"
                  f"Position: {role.position}",
            inline=True
        )
    
    embed.set_footer(text=f"Total auto-roles: {len(auto_roles[guild_id])}")
    await ctx.send(embed=embed)

# Add error handling for auto-role commands
@auto_role.error
@auto_role_on_join.error
@auto_role_on_verify.error
@auto_role_info.error
async def auto_role_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to manage auto-roles!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide all required arguments!")
    else:
        logger.error(f"Auto-role command error: {error}")
        await ctx.send("An error occurred while processing the command.")

# Bad word filter commands
@bot.command(name='badword')
@commands.has_permissions(administrator=True)
async def bad_word(ctx, action: str, *, word: str = None):
    """Manage banned words in the server
    Actions: add, remove, list, clear
    Example: !badword add badword"""
    if action.lower() not in ['add', 'remove', 'list', 'clear']:
        await ctx.send("Invalid action! Use: add, remove, list, or clear")
        return

    guild_id = ctx.guild.id
    if guild_id not in banned_words:
        banned_words[guild_id] = set()

    if action.lower() == 'add':
        if not word:
            await ctx.send("Please specify a word to ban!")
            return
        word = word.lower()
        if word in banned_words[guild_id]:
            await ctx.send(f"'{word}' is already in the banned words list!")
            return
        banned_words[guild_id].add(word)
        await ctx.send(f"Added '{word}' to banned words!")

    elif action.lower() == 'remove':
        if not word:
            await ctx.send("Please specify a word to remove!")
            return
        word = word.lower()
        if word not in banned_words[guild_id]:
            await ctx.send(f"'{word}' is not in the banned words list!")
            return
        banned_words[guild_id].remove(word)
        await ctx.send(f"Removed '{word}' from banned words!")

    elif action.lower() == 'list':
        if not banned_words[guild_id]:
            await ctx.send("No banned words set up!")
            return
        embed = discord.Embed(
            title="Banned Words",
            description="Words that will be automatically filtered",
            color=discord.Color.red()
        )
        # Split banned words into chunks of 10 for better display
        words_list = list(banned_words[guild_id])
        for i in range(0, len(words_list), 10):
            chunk = words_list[i:i+10]
            embed.add_field(
                name=f"Words {i+1}-{i+len(chunk)}",
                value="\n".join(f"• {word}" for word in chunk),
                inline=False
            )
        await ctx.send(embed=embed)

    elif action.lower() == 'clear':
        banned_words[guild_id].clear()
        await ctx.send("Cleared all banned words!")

@bot.command(name='badwordaction')
@commands.has_permissions(administrator=True)
async def bad_word_action(ctx, action: str):
    """Set the action to take when banned words are used
    Actions: delete, warn, timeout
    Example: !badwordaction warn"""
    if action.lower() not in ['delete', 'warn', 'timeout']:
        await ctx.send("Invalid action! Use: delete, warn, or timeout")
        return

    guild_id = ctx.guild.id
    if guild_id not in banned_words:
        banned_words[guild_id] = set()

    # Store the action in the banned_words dictionary
    banned_words[guild_id] = (banned_words[guild_id], action.lower())
    
    embed = discord.Embed(
        title="Bad Word Action Updated",
        description=f"Action set to: {action.lower()}",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="Available Actions",
        value="• delete: Only delete the message\n• warn: Delete and warn the user\n• timeout: Delete and timeout the user for 5 minutes",
        inline=False
    )
    await ctx.send(embed=embed)

# Ticket system commands
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green, emoji="🎫", custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild_id
        if guild_id not in ticket_counters:
            ticket_counters[guild_id] = 0
        ticket_counters[guild_id] += 1
        
        # Create ticket channel
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        # Get staff role if it exists
        staff_role = discord.utils.get(interaction.guild.roles, name="Staff")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        channel = await interaction.guild.create_text_channel(
            f"ticket-{ticket_counters[guild_id]}",
            overwrites=overwrites,
            category=interaction.channel.category
        )
        
        ticket_channels[channel.id] = {
            "user_id": interaction.user.id,
            "created_at": datetime.utcnow(),
            "status": "open"
        }
        
        embed = discord.Embed(
            title="Ticket Created",
            description=f"Welcome {interaction.user.mention}! Please describe your issue and a staff member will assist you shortly.",
            color=discord.Color.green()
        )
        embed.add_field(name="Ticket Information", value=f"Ticket ID: {ticket_counters[guild_id]}\nCreated by: {interaction.user.mention}")
        
        # Create ticket management view
        view = TicketManagementView()
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Ticket created! Please check {channel.mention}", ephemeral=True)

        # Add logging
        log_embed = discord.Embed(
            title="Ticket Created",
            description=f"A new ticket has been created",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        log_embed.add_field(name="Ticket ID", value=ticket_counters[guild_id])
        log_embed.add_field(name="Created by", value=interaction.user.mention)
        log_embed.add_field(name="Channel", value=channel.mention)
        await send_log(interaction.guild_id, log_embed)

class TicketManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("You don't have permission to close tickets!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id in ticket_channels:
            ticket_info = ticket_channels[channel.id]
            user = await interaction.guild.fetch_member(ticket_info["user_id"])
            
            embed = discord.Embed(
                title="Ticket Closed",
                description=f"This ticket has been closed by {interaction.user.mention}",
                color=discord.Color.red()
            )
            embed.add_field(name="Ticket Information", 
                          value=f"Created by: {user.mention}\n"
                                f"Created at: {ticket_info['created_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"Closed at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
            
            await interaction.response.send_message(embed=embed)
            
            # Archive the channel
            await channel.edit(archived=True, locked=True)
            ticket_channels[channel.id]["status"] = "closed"
            
            # Add logging
            log_embed = discord.Embed(
                title="Ticket Closed",
                description=f"A ticket has been closed",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            log_embed.add_field(name="Ticket ID", value=ticket_counters[interaction.guild_id])
            log_embed.add_field(name="Closed by", value=interaction.user.mention)
            log_embed.add_field(name="Channel", value=interaction.channel.mention)
            await send_log(interaction.guild_id, log_embed)
    
    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.blurple, emoji="✋", custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("You don't have permission to claim tickets!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id in ticket_channels:
            if ticket_channels[channel.id].get("claimed_by"):
                await interaction.response.send_message("This ticket is already claimed!", ephemeral=True)
                return
            
            ticket_channels[channel.id]["claimed_by"] = interaction.user.id
            embed = discord.Embed(
                title="Ticket Claimed",
                description=f"This ticket has been claimed by {interaction.user.mention}",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)

@bot.command(name='ticket')
@commands.has_permissions(administrator=True)
async def ticket(ctx, action: str = None):
    """Manage the ticket system
    Actions: setup, close, list
    Example: !ticket setup"""
    if not action:
        await ctx.send("Please specify an action: setup, close, or list")
        return

    if action.lower() == 'setup':
        embed = discord.Embed(
            title="🎫 Support Ticket System",
            description="Click the button below to create a support ticket.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="How to use",
            value="1. Click the 'Create Ticket' button\n"
                  "2. Describe your issue in the ticket\n"
                  "3. Wait for a staff member to assist you",
            inline=False
        )
        
        view = TicketView()
        await ctx.send(embed=embed, view=view)
        
    elif action.lower() == 'close':
        if ctx.channel.id in ticket_channels:
            ticket_info = ticket_channels[ctx.channel.id]
            user = await ctx.guild.fetch_member(ticket_info["user_id"])
            
            embed = discord.Embed(
                title="Ticket Closed",
                description=f"This ticket has been closed by {ctx.author.mention}",
                color=discord.Color.red()
            )
            embed.add_field(name="Ticket Information", 
                          value=f"Created by: {user.mention}\n"
                                f"Created at: {ticket_info['created_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"Closed at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
            
            await ctx.send(embed=embed)
            await ctx.channel.edit(archived=True, locked=True)
            ticket_channels[ctx.channel.id]["status"] = "closed"
        else:
            await ctx.send("This is not a ticket channel!")
            
    elif action.lower() == 'list':
        open_tickets = [ch for ch, info in ticket_channels.items() if info["status"] == "open"]
        closed_tickets = [ch for ch, info in ticket_channels.items() if info["status"] == "closed"]
        
        embed = discord.Embed(
            title="Ticket Statistics",
            color=discord.Color.blue()
        )
        embed.add_field(name="Open Tickets", value=str(len(open_tickets)), inline=True)
        embed.add_field(name="Closed Tickets", value=str(len(closed_tickets)), inline=True)
        embed.add_field(name="Total Tickets", value=str(len(ticket_channels)), inline=True)
        
        if open_tickets:
            open_ticket_list = "\n".join([f"<#{ch}>" for ch in open_tickets[:10]])
            if len(open_tickets) > 10:
                open_ticket_list += f"\n...and {len(open_tickets) - 10} more"
            embed.add_field(name="Recent Open Tickets", value=open_ticket_list, inline=False)
        
        await ctx.send(embed=embed)

@bot.event
async def on_guild_channel_delete(channel):
    """Clean up ticket data when a ticket channel is deleted"""
    if channel.id in ticket_channels:
        del ticket_channels[channel.id]

# Add error handling for ticket commands
@ticket.error
async def ticket_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to manage tickets!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide all required arguments!")
    else:
        logger.error(f"Ticket command error: {error}")
        await ctx.send("An error occurred while processing the command.")

# Logging system commands
@bot.command(name='setlog')
@commands.has_permissions(administrator=True)
async def set_log(ctx, channel: discord.TextChannel):
    """Set the logging channel for the server"""
    guild_id = ctx.guild.id
    log_channels[guild_id] = channel.id
    
    embed = discord.Embed(
        title="Logging System Setup",
        description=f"Logging channel set to {channel.mention}",
        color=discord.Color.green()
    )
    embed.add_field(
        name="Events that will be logged",
        value="• Moderation actions (ban, kick, mute, etc.)\n"
              "• Ticket events (create, close, claim)\n"
              "• Server events (member join/leave, role updates)\n"
              "• Channel events (create, delete, update)\n"
              "• Message events (deletions, edits)",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name='logchannel')
@commands.has_permissions(administrator=True)
async def view_log_channel(ctx):
    """View the current logging channel for the server"""
    guild_id = ctx.guild.id
    
    if guild_id not in log_channels:
        embed = discord.Embed(
            title="Logging Channel",
            description="No logging channel has been set up yet.",
            color=discord.Color.red()
        )
        embed.add_field(
            name="How to set up",
            value="Use `!setlog #channel` to set up a logging channel",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    channel = bot.get_channel(log_channels[guild_id])
    if not channel:
        embed = discord.Embed(
            title="Logging Channel",
            description="The logging channel no longer exists.",
            color=discord.Color.red()
        )
        embed.add_field(
            name="How to fix",
            value="Use `!setlog #channel` to set up a new logging channel",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="Logging Channel",
        description=f"Current logging channel: {channel.mention}",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="Events being logged",
        value="• Moderation actions\n"
              "• Ticket events\n"
              "• Server events\n"
              "• Channel events\n"
              "• Message events",
        inline=False
    )
    embed.add_field(
        name="How to change",
        value="Use `!setlog #channel` to set a different logging channel",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name='removelog')
@commands.has_permissions(administrator=True)
async def remove_log(ctx):
    """Remove the logging channel for the server"""
    guild_id = ctx.guild.id
    
    if guild_id not in log_channels:
        embed = discord.Embed(
            title="Logging Channel",
            description="No logging channel is currently set up.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    channel = bot.get_channel(log_channels[guild_id])
    del log_channels[guild_id]
    
    embed = discord.Embed(
        title="Logging Channel Removed",
        description=f"Logging channel {channel.mention if channel else 'Unknown'} has been removed.",
        color=discord.Color.green()
    )
    embed.add_field(
        name="How to set up again",
        value="Use `!setlog #channel` to set up a new logging channel",
        inline=False
    )
    await ctx.send(embed=embed)

# Add error handling for logging commands
@set_log.error
async def set_log_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to set up logging!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please specify a channel for logging!")
    else:
        logger.error(f"Logging setup error: {error}")
        await ctx.send("An error occurred while setting up logging.")

@view_log_channel.error
async def view_log_channel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to view logging settings!")
    else:
        logger.error(f"View log channel error: {error}")
        await ctx.send("An error occurred while viewing logging settings.")

@remove_log.error
async def remove_log_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to remove logging settings!")
    else:
        logger.error(f"Remove log channel error: {error}")
        await ctx.send("An error occurred while removing logging settings.")

async def send_log(guild_id: int, embed: discord.Embed):
    """Send a log message to the server's logging channel"""
    if guild_id in log_channels:
        try:
            channel = bot.get_channel(log_channels[guild_id])
            if channel:
                await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error sending log: {e}")

# Run the bot
if __name__ == "__main__":
    if not TOKEN:
        logger.error("No token found. Please set the DISCORD_TOKEN environment variable.")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")

