import discord
import asyncio
import pysmash
import pymongo
import pprint
from pymongo import MongoClient
import datetime
from random import *
import re
import yaml
import os

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
with open(os.path.join(__location__, "config.yaml"), 'r') as ymlfile:
    cfg = yaml.load(ymlfile)
username = cfg['mongodb']['user']
password = cfg['mongodb']['password']
client = discord.Client()
mClient = MongoClient('mongodb://%s:%s@127.0.0.1' % (username, password))
smash = pysmash.SmashGG()
mDb = mClient["database"]
users = mDb['users']
auth = mDb['discord_auth']
chars = mDb['characters']
tourneys = mDb['tourney']

#Todo: Move this to a config
rewards = [200,160,130,100,70,40,20,10,5,1]
allowed_platforms = ['xbox','ps4','pc']
allowed_regions = ['West Coast','East Coast','Oceania','South America','Asia','Middle East','Europe']
queue = {'ps4': {'West Coast':'','East Coast':'','Oceania':'','South America':'','Asia':'','Middle East':'','Europe':''},
'xbox':{'West Coast':'','East Coast':'','Oceania':'','South America':'','Asia':'','Middle East':'','Europe':''},
'pc':{'West Coast':'','East Coast':'','Oceania':'','South America':'','Asia':'','Middle East':'','Europe':''}}


def search_dictionaries(key, value, list_of_dictionaries):
    return [element for element in list_of_dictionaries if element[key] == value]

def add_points(name, amount, current_placement, last_placement):
    users.update_one({"name" : name}, {"$inc":{"points" : amount }})
    users.update_one({"name" : name}, {"$set":{"last_updated" : datetime.datetime.utcnow()}})

def apply_decay(name, days_idle, current_penalty, current_points):
    penalty = math.floor(days_idle/7)
    if (penalty > 7):
        penalty = 7
    if (penalty > current_penalty):
        users.update_one({"name" : name}, {"$set":{"decay_penalty" : penalty}})
        amount = math.floor(current_points * ( 1 - (0.1 * (penalty - 1))))
        if (amount > current_points):
            amount = -current_points
        users.update_one({"name" : name}, {"$set":{"points" : amount }})

async def decay_timer():
    await client.wait_until_ready()
    channel = discord.Object(id='channel_id_here')
    while not client.is_closed:
        await asyncio.sleep(604800)
        results = users.find({"last_updated" : { "$lte" : datetime.datetime.utcnow() - datetime.timedelta(days = 7)}})
        for result in results:
            apply_decay(result['name'], datetime.datetime.utcnow() - result['last_updated'], result['decay_penalty'], results['points'])
        await client.send_message(channel, "Applying decay, please wait warmly.")


@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

@client.event
async def on_message(message):
    user = message.author.id
    server = message.server.id
    uauth = auth.find_one( { "$and": [ { "user_id": user },  { "server": server } ] })
    if message.content.startswith('!help'):
        await client.send_message(message.channel, "```Commands: \n!help: shows you this \n!queue [region or cancel]: queues you for selected region (please only use in platform specific channels)\n!framedata [character] [optional:move]: gets framedata (not ready yet)```")
    if message.content.startswith('!framedata'):
        parts = message.content.split(" ")
        character = parts[1]
        if (len(parts) > 2):
            move = parts[2]
            result = chars.find_one( { "$and": [ { "name": character },  { "move": move } ] })
            if (result):
                em=discord.Embed(title=character, description=move)
                em.add_field(name="Start Up", value=result['start_up'])
                em.add_field(name="Active", value=result['active'])
                em.add_field(name="Recovery", value=result['recovery'])
                em.add_field(name="Frame Advantage", value=result['fram_adv'])
                em.add_field(name="Attribute", value=result['attribute'])
                em.add_field(name="Damage", value=result['damage'])
                await client.send_message(message.channel, embed=em)
            else:
                await client.send_message(message.channel, "Move not found")
        else:
            results = chars.find({"name": character})
            if (results.count()): 
                for result in results:
                    em=discord.Embed(title=character, description=move)
                    em.add_field(name="Start Up", value=result['start_up'])
                    em.add_field(name="Active", value=result['active'])
                    em.add_field(name="Recovery", value=result['recovery'])
                    em.add_field(name="Frame Advantage", value=result['fram_adv'])
                    em.add_field(name="Attribute", value=result['attribute'])
                    em.add_field(name="Damage", value=result['damage'])
                    await client.send_message(message.author, embed=em)
            else:
                await client.send_message(message.channel, "Who is " + character + "?")
    if message.content.startswith('!queue'):
        platform = message.channel.name.lower()
        parts = message.content.split(" ")
        if len(parts) > 1 and platform in allowed_platforms:
            country = parts[1]
            region_found = False
            if country in allowed_regions:
                region_found = True
            elif  len(parts) > 2:
                country = parts[1] + " " + parts[2]
                if country in allowed_regions:
                    region_found = True
            if platform in allowed_platforms and region_found:
                if queue[platform][country]:
                    player = queue[platform][country]
                    if player == user:
                        await client.send_message(message.channel, "Hey,  Past <@" + player + ">, Future <@" + user + "> wants to fight you!")
                    else:
                        queue[platform][country] = None
                        await client.send_message(message.channel, "Hey, <@" + player + ">, <@" + user + "> is available to fight you!")
                else:
                    queue[platform][country] = user
                    name = message.author.nick
                    if not name:
                        name = message.author.name
                    await client.send_message(message.channel, "Waiting for a challenge for " + name + ".")
            elif platform in allowed_platforms and country == 'cancel':
                found = False
                name = message.author.nick
                if not name:
                    name = message.author.name
                for region, player in queue[platform].items():
                    if player == user:
                        found = True
                        queue[platform][region] = None
                        await client.send_message(message.channel, "Removed " + name + " from the " + region + " queue.")
                if not found:
                    await client.send_message(message.channel, "Hey, " + name + " you're not actually queued for anything.")
            else:
                await client.send_message(message.channel, "That is not a valid region.  Usage is !queue [West Coast, East Coast, South America, Oceania, Asia, Middle East, Europe] or !queue cancel to leave the queue")
        elif not platform in allowed_platforms:
            await client.send_message(message.channel, "What kind of platform is " + platform + "?  Please only use in the appropriate channel!")
        else:
            await client.send_message(message.channel, "Please see !help for proper usage.")
    if (uauth):
        if message.content.startswith('!test'):
            await client.send_message(message.channel, "Authenticate Okay!")
        if message.content.startswith('!decay'):
            results = users.find({"last_updated" : { "$lte" : datetime.datetime.utcnow() - datetime.timedelta(days = 7)}})
            for result in results:
                apply_decay(result['name'], datetime.datetime.utcnow() - result['last_updated'], result['decay_penalty'], results['points'])
            await client.send_message(message.channel, "Applied decay to " + len(results) + " users.")
        if message.content.startswith('!ranking'):
            results = users.find(batch_size=10).sort('points', pymongo.DESCENDING)
            em=discord.Embed(title="Rankings", description="Ranking by Points")
            for result in results:
                em.add_field(name=result['name'],value=result['points'],inline=False)
            await client.send_message(message.channel, embed=em)
        if message.content.startswith('!process'):
            parts = message.content.split(" ")
            tournament = parts[1]
            game = parts[2]
            try:
                players = smash.tournament_show_players(tournament,game)
                for player in players:
                    user = users.find_one({"name" : player['tag']});
                    fPlacement = player['final_placement']
                    points = 0;
                    if fPlacement < 9:
                        points = rewards[fPlacement - 1]
                    if user:
                        points = points
                        if points < 0:
                            points = 0
                        addpoints(player['tag'], points)
                    else:
                        payload = {'name' : player['tag'], 'last_updated' : datetime.datetime.utcnow(), 'points' : points, 'last_placement' : fPlacement, 'decay_penalty': 0}
                        users.insert_one(payload)
                await client.send_message(message.channel, "Done.")
            except pysmash.exceptions.ValidationError as e:
                a = re.search("\[(.*?)\]",e.args[0])
                await  client.send_message(message.channel, "Game not found, valid games are: " + a.group(1) + ".")
            except pysmash.exceptions.ResponseError:
                await client.send_message(message.channel, "Tournament not found.")
        if message.content.startswith('!tourney'):
            parts = message.content.split(" ")
            tournament = parts[1]
            game = parts[2]
            try:
                players = smash.tournament_show_players(tournament,game)
                em=discord.Embed(title="Results for " + tournament, description="Results for " + game)
                for x in range(1,4):
                    player = search_dictionaries('final_placement',x,players)[0]
                    if player:
                        tag = player["tag"]
                    else:
                        tag = "Not Found"
                    em.add_field(name=placement[x - 1],value=tag,inline=False)
                await client.send_message(message.channel, embed=em)
            except pysmash.exceptions.ValidationError as e:
                a = re.search("\[(.*?)\]",e.args[0])
                await  client.send_message(message.channel, "Game not found, valid games are: " + a.group(1) + ".")
            except pysmash.exceptions.ResponseError:
                await client.send_message(message.channel, "Tournament not found.")


            
            

#client.loop.create_task(decay_timer())
client.run(cfg['discord']['token'])
