import discord
from discord import app_commands
from discord.ui import Modal, TextInput
from discord.ext import commands
import aiohttp
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = app_commands.CommandTree(bot)

# ---------------- TruckersMP APIs ----------------
TMP_PLAYER_API = "https://api.truckersmp.com/v2/player/"
TMP_VTC_API = "https://api.truckersmp.com/v2/vtc/"
TMP_BANS_API = "https://api.truckersmp.com/v2/bans/"

class VTCIDModal(Modal, title="Enter Your VTC ID"):
    vtc_id = TextInput(
        label="VTC ID",
        placeholder="e.g. 1234",
        required=True,
        style=discord.TextInputStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            vtc_id_num = int(self.vtc_id.value.strip())
        except ValueError:
            await interaction.followup.send("❌ Invalid VTC ID. Must be a number.", ephemeral=True)
            return

        async with aiohttp.ClientSession() as session:
            vtc_url = f"{TMP_VTC_API}{vtc_id_num}"
            async with session.get(vtc_url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Failed to fetch VTC. Check the ID.", ephemeral=True)
                    return
                vtc_data = await resp.json()

            if

 vtc_data.get("error"):
                await interaction.followup.send(f"❌ Error: {vtc_data.get('response', 'Unknown')}", ephemeral=True)
                return

            members = vtc_data["response"].get("members", [])
            if not members:
                await interaction.followup.send("ℹ️ This VTC has no members.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"{vtc_data['response']['name']} Members",
                description=f"Total: {len(members)} | [View on TruckersMP](https://truckersmp.com/vtc/{vtc_id_num})",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            logo = vtc_data["response"].get("logo")
            if logo:
                embed.set_thumbnail(url=logo)

            shown = min(15, len(members))  # Limit to avoid timeouts/rate limits
            for member in members[:shown]:
                player_id = member["id"]
                name = member["username"]
                role = member["role"]
                vtc_join = member.get("join_date", "N/A")

                # Player details
                async with session.get(f"{TMP_PLAYER_API}{player_id}") as p:
                    p_data = await p.json() if p.status == 200 else {}
                    player = p_data.get("response", {})

                # Bans
                async with session.get(f"{TMP_BANS_API}{player_id}") as b:
                    b_data = await b.json() if b.status == 200 else {}
                    ban_count = len(b_data.get("response", []))

                details = (
                    f"**Role:** {role}\n"
                    f"**TMP ID:** {player.get('id', 'N/A')}\n"
                    f"**Steam ID:** {player.get('steamID64', 'N/A')}\n"
                    f"**Joined TMP:** {player.get('joinDate', 'N/A')[:10]}\n"
                    f"**Joined VTC:** {vtc_join[:10]}\n"
                    f"**Bans:** {ban_count}"
                )

                embed.add_field(name=f"{name}", value=details, inline=False)

            if len(members) > shown:
                embed.set_footer(text=f"Showing {shown}/{len(members)} members • Limited for performance")

            await interaction.followup.send(embed=embed)

@tree.command(name="vtc_members", description="Fetch members of a TruckersMP VTC")
async def vtc_members(interaction: discord.Interaction):
    await interaction.response.send_modal(VTCIDModal())

@bot.event
async def on_ready():
    await tree.sync()
    print(f"🚀 Bot is online as {bot.user}")

bot.run(BOT_TOKEN)
