# vtcs/upcoming.py

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from datetime import datetime, timezone, timedelta

def setup_upcoming(bot: commands.Bot, get_user_vtc_name):
    """
    get_user_vtc_name(user_id) -> str
    Should return the user's VTC name or None if they have none.
    """

    @bot.tree.command(name="upcoming", description="Show upcoming TruckersMP events for your VTC")
    async def upcoming(interaction: discord.Interaction):
        user_id = interaction.user.id
        vtc_name = get_user_vtc_name(user_id)
        if not vtc_name:
            return await interaction.response.send_message(
                "❌ You don’t have a VTC registered.", ephemeral=True
            )

        await interaction.response.defer(thinking=True, ephemeral=True)

        # Fetch upcoming events from TruckersMP API
        api_url = "https://api.truckersmp.com/v2/events"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        return await interaction.followup.send(
                            f"❌ TruckersMP API returned HTTP {resp.status}.", ephemeral=True
                        )
                    data = await resp.json()
        except Exception as e:
            return await interaction.followup.send(f"❌ Failed to fetch events: `{e}`", ephemeral=True)

        events = data.get("response", [])

        # Filter events by VTC name (creator)
        filtered = []
        for evt in events:
            creator = evt.get("creator", {})
            creator_name = creator.get("name")
            if creator_name and creator_name.lower() == vtc_name.lower():
                filtered.append(evt)

        if not filtered:
            return await interaction.followup.send("❌ No upcoming events found for your VTC.", ephemeral=True)

        # Sort by start time
        filtered.sort(key=lambda e: e.get("meetupDateTime") or "")

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

            embed = discord.Embed(
                title=name,
                description=f"**Start:** {time_text}\n[Event Link]({event_link})",
                color=discord.Color.blue()
            )

            if event_banner:
                embed.set_image(url=event_banner)
            if creator_avatar:
                embed.set_thumbnail(url=creator_avatar)

            embed.set_footer(text=f"Creator: {vtc_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)
