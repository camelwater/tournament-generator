import discord
from discord.ext import commands
from classes.generator import Generator
from classes.Channels import RegChannel, GenChannel
from classes.registrator import Registrator
import bot
import utils.discord_utils as discord_utils

# TODO: need to add some sort of check for cross-cog commands (Registration commands can't be used in generation channels, and vice versa)

class Generation(commands.Cog):
    def __init__(self, bot: bot.TournamentBOT):
        self.bot = bot
    
    async def send_temp_messages(self, ctx, *args):
        try:
            await ctx.send('\n'.join(args), delete_after=25)
        except discord.errors.Forbidden:
            await ctx.send(f"I do not have adequate permissions. Check `{ctx.prefix}help` for a list of the permissions that I need.")
    async def send_messages(self,ctx, *args):
        try:
            await ctx.send('\n'.join(args))
        except discord.errors.Forbidden:
            await ctx.send(f"I do not have adequate permissions. Check `{ctx.prefix}help` for a list of the permissions that I need.")
    
    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if ctx.command not in self.bot.get_cog('Generation').get_commands(): return
        self.set_instance(ctx)

    def set_instance(self, ctx: commands.Context):
        '''
        Add a GenChannel instance into the generator_instances dictionary if it isn't present.
        '''

        channel_id = ctx.channel.id
        
        if channel_id in self.bot.generator_instances: 
            self.bot.generator_instances[channel_id].prefix = ctx.prefix
            return

        self.bot.generator_instances[channel_id] = GenChannel(self.bot, ctx)

    async def cog_before_invoke(self, ctx):
        self.set_instance(ctx)
    
    async def check_callable(self, ctx: commands.Context, command):
        if command in ['start']:
            if not self.bot.generator_instances[ctx.channel.id].reg_channel:
                await ctx.send(f"You need to have an open tournament and have finished player registrations before using `{ctx.prefix}{command}.`")
                return True
            reg_open = self.bot.registrator_instances[self.bot.generator_instances[ctx.channel.id].reg_channel].open
            if reg_open is None or reg_open is True:
                await ctx.send(f"You need to finish player registrations before using `{ctx.prefix}{command}`.")
                return True
        elif not self.bot.generator_instances[ctx.channel.id].is_active():
            await ctx.send(f"You need to have an active tournament before using `{ctx.prefix}{command}`.")
            return True
        elif command!="finish" and self.bot.generator_instances[ctx.channel.id].is_finished():
            await ctx.send(f"The tournament has already been finished. You can end the tournament with `{ctx.prefix}finish` or open a new one with `{ctx.prefix}open`.")
            return True

        return False

    @commands.command(aliases=['o', 'openreg', 'openregistration'])
    @commands.has_permissions(administrator=True)
    async def open(self, ctx: commands.Context, reg_channel_id: str, sheets_id: str, self_rating: bool = False, open: bool = True, random: bool = False):
        '''
        Opens a channel for tournament registrations.
        '''
        reg_channel_id = int(reg_channel_id.lstrip("<#").rstrip(">"))
        
        if reg_channel_id == ctx.channel.id:
            return await ctx.send("You cannot set the registration channel to this channel.")
        if reg_channel_id in self.bot.generator_instances:
            return await ctx.send("You cannot set this channel as the registration channel because this channel is already being used as a generation channel.")
        if reg_channel_id in self.bot.registrator_instances:
            return await ctx.send("You cannot set this channel as the registration channel because it is already being used as a registration channel.")

        if not ctx.guild.get_channel(reg_channel_id):
            return await ctx.send("The registration channel you provided was invalid.")
        
        if self.bot.generator_instances[ctx.channel.id].is_open():
            #did `,reset` but there's an existing open tournament instance
            pass

        self.bot.generator_instances[ctx.channel.id].setup(reg_channel_id, sheets_id, self_rating, open, random)
        self.bot.registrator_instances[reg_channel_id] = RegChannel(self.bot, ctx)
        self.bot.registrator_instances[reg_channel_id].setup(ctx.channel.id, sheets_id, self_rating)
        
        await ctx.send(f"I am now watching registrations in <#{reg_channel_id}>.")
    
    @open.error
    async def open_error(self, ctx: commands.Context, error):

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Usage: `{ctx.prefix}open [registrationChannelID] [sheetsID] (rating=False) (open=True) (random=False)`")
        elif isinstance(error, commands.BadArgument):
            await self.send_messages(ctx, f"Error processing paramters: {', '.join(error.args)}", 
                f"Usage: `{ctx.prefix}open [registrationChannelID] [sheetsID] (rating=False) (open=True) (random=False)`")

    # @commands.command(aliases=['end', 'endreg', 'closereg', 'stopreg'])
    # async def close(self, ctx: commands.Context):
    #     '''
    #     Closes the registration.

    #     ''' 
    #     reg_channel_id = self.bot.generator_instances[ctx.channel.id].get_reg_channel()
    #     mes = self.bot.registrator_instances[reg_channel_id].close_reg()
    #     await ctx.send(mes)

    @commands.command(aliases=['initialize', 'init', 'create', 'begin'])
    @commands.has_permissions(administrator=True)
    async def start(self, ctx: commands.Context, sheets_id: str = None, self_rating: bool = False, open = True, random = False):
        '''
        Load player registrations and initialize the tournament.
        '''
        if await self.check_callable(ctx, "start"): return

        mes, round, file_content = self.bot.generator_instances[ctx.channel.id].start_tournament()
        dir = './temp_files/'
        filename = f"round_{round}_matchups-{ctx.channel.id}.txt"
        r_file = discord_utils.create_temp_file(filename, file_content, dir=dir)
        discord_utils.delete_file(dir+filename)
        await ctx.send(mes)
        await ctx.send(file = discord.File(fp=r_file, filename=filename))
    
    @commands.command(aliases=['a', 'adv'])
    @commands.has_permissions(administrator=True)
    async def advance(self, ctx: commands.Context, *, players_arg):
        '''
        Advance a group of players to the next round.
        '''
        #TODO: process different player args (have to split by newlines or another special character)
        if await self.check_callable(ctx, "advance"): return
        players = players_arg.split("\n")
        players = [player.strip().lstrip("<@").lstrip("<@!").rstrip(">") for player in players]

        mes = self.bot.generator_instances[ctx.channel.id].advance_players(players)
        await ctx.send(mes)
    
    @advance.error
    async def advance_error(self, ctx: commands.Context, error):
        self.set_instance(ctx)
        if await self.check_callable(ctx, "advance"): return

        if isinstance(error, commands.MissingRequiredArgument):
            await self.send_temp_messages(ctx, f"Usage: `{ctx.prefix}advance [player, ...]`")
    
    @commands.command(aliases=['ua', 'unadv'])
    @commands.has_permissions(administrator=True)
    async def unadvance(self, ctx: commands.Context, *, players_arg):
        '''
        Unadvance a group of players from the next round advanced pool.
        '''
        #TODO: process different player args (have to split by newlines or another special character)
        if await self.check_callable(ctx, "unadvance"): return
        players = players_arg.split("\n")
        players = [player.strip().lstrip("<@").lstrip("<@!").rstrip(">") for player in players]

        mes = self.bot.generator_instances[ctx.channel.id].unadvance_players(players)
        await ctx.send(mes)
    
    @unadvance.error
    async def unadvance_error(self, ctx: commands.Context, error):
        self.set_instance(ctx)
        if await self.check_callable(ctx, "unadvance"): return

        if isinstance(error, commands.MissingRequiredArgument):
            await self.send_temp_messages(ctx, f"Usage: `{ctx.prefix}unadvance [player, ...]`")
    
    @commands.command(aliases=['increment', 'next'])
    @commands.has_permissions(administrator=True)
    async def nextround(self, ctx: commands.Context):
        '''
        Move on to the next round.
        '''
        if await self.check_callable(ctx, "nextround"): return

        mes, round, file_content = self.bot.generator_instances[ctx.channel.id].next_round()
        if file_content is None:
            return await ctx.send(mes)
        dir = './temp_files/'
        filename = f"round_{round}_matchups-{ctx.channel.id}.txt"
        r_file = discord_utils.create_temp_file(filename, file_content, dir=dir)
        discord_utils.delete_file(dir+filename)
        await ctx.send(mes)
        await ctx.send(file = discord.File(fp=r_file, filename=filename))
    
    @commands.command(aliases=['rs', 'roundstatus'])
    @commands.has_permissions(administrator=True)
    async def status(self, ctx: commands.Context):
        '''
        Get the status (matchups that have finished and matchups that are still in progress) of the current round.
        '''

        if await self.check_callable(ctx, "status"): return

    @commands.command(aliases=['rr', 'roundresults', 'res'])
    @commands.has_permissions(administrator=True)
    async def results(self, ctx: commands.Context, round = -1):
        '''
        Get the results of a specific round (all matchups and winners of each matchup).
        '''
        if await self.check_callable(ctx, "results"): return

    @commands.command(aliases=['stop', 'done', 'reset', 'endtournament', 'clear'])
    @commands.has_permissions(administrator=True)
    async def finish(self, ctx: commands.Context):
        '''
        Finish the tournament, update the results to the Google Sheet, and clear the generation instance.
        '''
        # if await self.check_callable(ctx, "finish"): return
        gen_instance = self.bot.generator_instances[ctx.channel.id]
        if not gen_instance.is_active():
            return await ctx.send("You don't have an active tournament to stop.")

        if gen_instance.is_finished():
            gen_instance.end_tournament()
            await ctx.send(f"Tournament has been ended. Congratulations to the winner: {gen_instance.get_winner().get_displayName()}!")
        else:
            await ctx.send(f"Tournament has been reset. Do `{ctx.prefix}open` to open a new tournament.")
        self.bot.generator_instances.pop(ctx.channel.id)

def setup(bot):
    bot.add_cog(Generation(bot))