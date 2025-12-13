# vtcs/upcoming.py

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime, timezone, timedelta

def setup_upcoming(bot: commands.Bot, get_user_vtc_name):
    """
    Setup the /upcoming command.

    get_user_vtc_name(user_id) -> str
    Should return the user's VTC name or None if they have none.
    """

    @bot.tree.command(name="upcoming", description="Show upcoming TruckersMP events for your VTC")
    async def upcoming(interaction: discord.Interaction):
        try:
            user_id = interaction.user.id
            vtc_name = get_user_vtc_name(user_id)
            if not vtc_name:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ You don’t have a VTC registered.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ You don’t have a VTC registered.", ephemeral=True
                    )
                return

            await interaction.response.defer(thinking=True, ephemeral=True)

            # Fetch all upcoming events
            api_url = "https://api.truckersmp.com/v2/events"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url) as resp:
                        if resp.status != 200:
                            msg = f"❌ TruckersMP API returned HTTP {resp.status}."
                            if not interaction.response.is_done():
                                await interaction.response.send_message(msg, ephemeral=True)
                            else:
                                await interaction.followup.send(msg, ephemeral=True)
                            return
                        data = await resp.json()
            except Exception as e:
                msg = f"❌ Failed to fetch events: `{e}`"
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                return

            events = data.get("response", [])

            # Filter events by VTC name (creator)
            filtered = []
            for evt in events:
                creator = evt.get("creator", {})
                creator_name = creator.get("name")
                if creator_name and creator_name.lower() == vtc_name.lower():
                    filtered.append(evt)

            if not filtered:
                msg = "❌ No upcoming events found for your VTC."
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                return

            # Sort by start time
            filtered.sort(key=lambda e: e.get("meetupDateTime") or "")

            # Create a single embed for all upcoming events
            embed = discord.Embed(
                title=f"Upcoming Events for {vtc_name}",
                color=discord.Color.blue()
            )

            for evt in filtered[:10]:  # Show max 10 events
                name = evt.get("name")
                event_link = f"https://truckersmp.com/events/{evt.get('id')}"
                start_str = evt.get("meetupDateTime")
                event_banner = evt.get("banner")
                creator_avatar = None
                creator = evt.get("creator", {})
                if isinstance(creator, dict):
                    creator_avatar = creator.get("avatar") or creator.get("logo")

                # Format time
                try:
                    dt = datetime.fromisoformat(start_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                    utc_str = dt.strftime("%Y-%m-%d %H:%M UTC")
                    npt_str = (dt + timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M NPT")
                    time_text = f"{utc_str} | {npt_str}"
                except Exception:
                    time_text = "Unknown time"

                embed.add_field(
                    name=name,
                    value=f"**Start:** {time_text}\n[Event Link]({event_link})",
                    inline=False
                )

                # Set banner only once
                if event_banner and embed.image.url is None:
                    embed.set_image(url=event_banner)
                if creator_avatar and embed.thumbnail.url is None:
                    embed.set_thumbnail(url=creator_avatar)

            embed.set_footer(text=f"Creator: {vtc_name}")

            # Send embed safely
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"[ERROR] /upcoming command: {e}")
            msg = "❌ An unexpected error occurred."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
