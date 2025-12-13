# vtcs/neppath_events.py
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime, timezone, timedelta

def setup_neppath_events(bot: commands.Bot):
    """
    Setup /events command for NepPath VTC.
    """

    @bot.tree.command(
        name="events",
        description="Show NepPath VTC events on a specific date"
    )
    @app_commands.describe(
        date="Date in dd/mm/yy format, e.g. 25/12/25"
    )
    async def events(interaction: discord.Interaction, date: str):
        try:
            vtc_name = "NepPath"

            # Parse date dd/mm/yy
            try:
                query_date = datetime.strptime(date, "%d/%m/%y").date()
            except Exception:
                await interaction.response.send_message("❌ Invalid date format. Use dd/mm/yy.", ephemeral=True)
                return

            await interaction.response.defer(thinking=True)

            # Fetch all events
            api_url = "https://api.truckersmp.com/v2/events"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ TruckersMP API returned HTTP {resp.status}.")
                        return
                    data = await resp.json()

            events = data.get("response", [])

            # Filter by NepPath and date
            matched_events = []
            for evt in events:
                creator = evt.get("creator") or {}
                creator_name = creator.get("name") if isinstance(creator, dict) else None
                if creator_name and creator_name.lower() == vtc_name.lower():
                    start_str = evt.get("meetupDateTime")
                    if start_str:
                        try:
                            dt = datetime.fromisoformat(start_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                            if dt.date() == query_date:
                                matched_events.append(evt)
                        except:
                            continue

            if not matched_events:
                await interaction.followup.send(f"❌ No events found for {vtc_name} on {date}.")
                return

            # Send embed for each event
            for evt in matched_events:
                name = evt.get("name") or "Unnamed Event"
                event_link = f"https://truckersmp.com/events/{evt.get('id')}"
                start_str = evt.get("meetupDateTime")
                event_banner = evt.get("banner")
                creator_avatar = None
                creator = evt.get("creator") or {}
                if isinstance(creator, dict):
                    creator_avatar = creator.get("avatar") or creator.get("logo")

                # Format time
                time_text = "Unknown time"
                if start_str:
                    try:
                        dt = datetime.fromisoformat(start_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                        utc_str = dt.strftime("%Y-%m-%d %H:%M UTC")
                        npt_str = (dt + timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M NPT")
                        time_text = f"{utc_str} | {npt_str}"
                    except:
                        pass

                embed = discord.Embed(
                    title=f"{name} | {vtc_name}",
                    description=f"**Start:** {time_text}\n[Event Link]({event_link})",
                    color=discord.Color.blue()
                )

                if event_banner:
                    embed.set_image(url=event_banner)
                if creator_avatar:
                    embed.set_thumbnail(url=creator_avatar)

                embed.set_footer(text=f"VTC: {vtc_name}")

                await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"[ERROR] /events: {e}")
            await interaction.followup.send("❌ An unexpected error occurred.")
