import os.path
import asyncio
import pygsheets

from asgiref.sync import sync_to_async

from cells import sheet_index


CHARACTER_INDEX = sheet_index['character']


# Necessary permissions to interact with google sheets.
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

BASE_STATS = ['nature', 'will', 'health', 'circles', 'resources']
SKILL_LIST = ['administrator', 'apiarist', 'archivist', 'armorer', 'baker', 'boatcrafter',
                'brewer', 'carpenter', 'cartographer', 'cook', 'fighter', 'glazier', 'haggler',
                'harvester', 'healer', 'hunter', 'insectrist', 'instructor', 'laborer',
                'loremouse', 'manipulator', 'militarist', 'miller', 'orator', 'pathfinder', 
                'persuader', 'potter', 'scientist', 'scout', 'smith', 'stonemason',
                'survivalist', 'weather watcher', 'weaver']
PROGRESSIONS = BASE_STATS + SKILL_LIST



class SheetManager():
    def __init__(self, creds_path, db_manager):
        self.creds_path = creds_path
        self.db_manager = db_manager
        self.sheets_cache = {}
        self.profile_selector_cache_by_message = {}
        self.profile_selector_cache_by_request = {}
        self.lock = asyncio.Lock()


    async def initialize(self):
        async with self.lock:
            # Just test the authentication to google services via service account
            print("  Authenticating to google web services...")
            await self.get_gc()
            print("  Done.")


    def _generate_request_key(self, user, channel):
        return str(user.id) + "_" + str(channel.id)


    async def uncache_profile_selector(self, profile_selector):
        async with self.lock:
            key = self._generate_request_key(profile_selector.owner, profile_selector.message)
            del self.profile_selector_cache_by_message[profile_selector.message.id]
            del self.profile_selector_cache_by_request[key]


    async def cache_profile_selector(self, profile_selector):
        async with self.lock:
            key = self._generate_request_key(profile_selector.owner, profile_selector.message)
            self.profile_selector_cache_by_message[profile_selector.message.id] = profile_selector
            self.profile_selector_cache_by_request[key] = profile_selector
    

    async def get_gc(self):
        return await sync_to_async(pygsheets.authorize)(service_file=self.creds_path)


    async def handle_event(self, user, reaction):
        # If not a "roll" message, bail
        if reaction.message.id in self.profile_selector_cache_by_message:
            # If the reaction is from the owner, and a valid option, interpet it. Otherwise, purge.
            profile_selector = self.profile_selector_cache_by_message[reaction.message.id]
            if profile_selector.owner.id == user.id and reaction.count > 1:
                await profile_selector.select(reaction=reaction)
            else:
                await reaction.remove(user)
        
    
    async def register_profile(self, channel, user, key):
        was_added = await self.db_manager.add_profile(user, key)
        msg = 'Profile registered' if was_added else 'A profile already exists with that key'
        await channel.send(f'{user.mention} - {msg}.')


    async def unregister_profile(self, channel, user, key):
        was_deleted = await self.db_manager.delete_profile(user, key)
        msg = 'Profile unregistered' if was_deleted else 'No profile found with that key'
        await channel.send(f'{user.mention} - {msg}.')


    async def use_profile(self, user, key):
        sheet = self.sheets_cache[user.id] if user.id in self.sheets_cache else GoogleBackedSheet(self, key)
        await self.db_manager.update_current(user, key)
        self.sheets_cache[user.id] = sheet


    async def initiate_choose_profile(self, user, channel):
        key = self._generate_request_key(user, channel)
        if key in self.profile_selector_cache_by_request:
            await self.profile_selector_cache_by_request[key].cancel()
        
        profile_selector = ProfileSelector(self, user, channel)
        await profile_selector.initialize()
        await self.cache_profile_selector(profile_selector)
        profile_keys = await self.db_manager._get_profile_keys(user)
        if not profile_keys:
            profile_selector.message.edit(f'{user.mention} - No profiles registered. Register with `!profile register <url|key>`.')
        await profile_selector.offer_profiles(profile_keys)
        

    async def display(self, user, channel):
        if user.id not in self.sheets_cache:
            key = await self.db_manager.get_current(user)
            if key:
                await self.use_profile(user, key)

        if user.id not in self.sheets_cache:
            return await channel.send(f'{user.mention} - No profile selected. Select with `!profile select`.')

        sheet = self.sheets_cache[user.id]
        await sheet.pull()
        msg = f'''```
Name: {sheet.name}
Nature: {sheet.get_rating('nature')}
Health: {sheet.get_rating('health')}
Will: {sheet.get_rating('will')}
```'''
        return await channel.send(f'{user.mention} - Your current profile:\n{msg}')        



class ProfileSelector():
    def __init__(self, manager, owner, channel):
        self.manager = manager
        self.owner = owner
        self.channel = channel
        self.profile_choices = {}
        self.lock = asyncio.Lock()


    async def initialize(self):
        self.message = await self.channel.send(f'{self.owner.mention} - Initializing...')


    async def offer_profiles(self, profiles):
        nums = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        
        for i in range(len(profiles)):
            self.profile_choices[nums[i]] = profiles[i]
        
        choices = '\n'.join(['> ' + nums[i] + '  -  `' + profiles[i] + '`' for i in range(len(profiles))])
        msg = f'{self.owner.mention} - Select a profile\n\n{choices}'
        await self.message.edit(content=msg)
        await self.message.clear_reactions()
        for emoji in nums[:len(profiles)]:
            await self.message.add_reaction(emoji)
        await self.message.add_reaction('❌')


    async def cancel(self):
        await self.message.edit(content=f'{self.owner.mention} - Profile select cancelled.')
        await self.message.clear_reactions()
        await self.manager.uncache_profile_selector(self)


    async def select(self, reaction=None):
        # Lock prevents responses from interrupting previous runs while finishing
        # work, like loading emoji options for a particular question.
        async with self.lock:
            # Assess the response to the previous prompt.
            # Cancel button - close out the builder.
            if reaction and reaction.emoji == '❌':
                print('blah')
                await self.cancel()
                return
            else:
                await self.message.edit(content=f'{self.owner.mention} - Using profile `{self.profile_choices[reaction.emoji]}`')
                await self.manager.use_profile(self.owner, self.profile_choices[reaction.emoji])
                await self.message.clear_reactions()
                await self.manager.uncache_profile_selector(self)





class GoogleBackedSheet():
    def __init__(self, manager, google_sheet_key):
        self.manager = manager
        self.google_sheet_key = google_sheet_key


    async def access_sheet(self):
        gc = await self.manager.get_gc()
        spreadsheet = await sync_to_async(gc.open_by_key)(self.google_sheet_key)
        worksheet = await sync_to_async(spreadsheet.worksheet_by_title)('Character Sheet')
        return worksheet


    async def pull(self):
        '''Pulls all data from a sheet to local cache'''
        sheet = await self.access_sheet()
        data = await sync_to_async(sheet.get_all_values)()

        # do translations
        self.player = self._access(data, CHARACTER_INDEX['player'])
        self.name = self._access(data, CHARACTER_INDEX['name'])
        self.home = self._access(data, CHARACTER_INDEX['home'])
        self.age = self._access(data, CHARACTER_INDEX['age'])
        self.fur = self._access(data, CHARACTER_INDEX['fur'])
        self.rank = self._access(data, CHARACTER_INDEX['rank'])
        self.specialty = self._access(data, CHARACTER_INDEX['specialty'])
        self.cloak = self._access(data, CHARACTER_INDEX['cloak'])
        self.weapon = self._access(data, CHARACTER_INDEX['weapon'])

        for base in BASE_STATS:
            val = {
                'rating': self._access_try_int(data, CHARACTER_INDEX[base]['rating']),
                'success': self._access_try_int(data, CHARACTER_INDEX[base]['success']),
                'fail': self._access_try_int(data, CHARACTER_INDEX[base]['fail'])
            }
            setattr(self, base, val)

        # Initialize bare skills, then populate from sheet
        for skill in SKILL_LIST:
            setattr(self, skill, { 'rating': None, 'success': 0, 'fail': 0 })

        for skill in CHARACTER_INDEX['skills']:
            name = self._access(data, skill['name']).lower()
            # Missing skill in sheet, empty space
            if not name:
                continue
            # Skill with bad name in sheet, big deal
            if name not in SKILL_LIST:
                continue
            val = {
                'rating': self._access_try_int(data, skill['rating']),
                'success': self._access_try_int(data, skill['success']),
                'fail': self._access_try_int(data, skill['fail']),
            }
            setattr(self, name, val)


    def get_success(self, key):
        return self._get_skill_subvalue(key, 'success')


    def get_fail(self, key):
        return self._get_skill_subvalue(key, 'fail')


    def get_rating(self, key):
        return self._get_skill_subvalue(key, 'rating')


    def check_valid_skill(self, skill):
        return skill in PROGRESSIONS


    def _get_skill_subvalue(self, key, subvalue):
        return getattr(self, key)[subvalue] if hasattr(self, key) else None


    def _access(self, data, cell):
        col = ord(cell[0]) - ord('A')
        row = int(cell[1:]) - 1
        return data[row][col]


    def _access_try_int(self, data, cell):
        # Convert to an int if possible. If not, return as-is
        val = self._access(data, cell)
        try:
            val = int(val)
        except:
            if val:
                val = val.lower()
        return val


    async def _render_rating(self, user, skill, progress):
        sheet = self.sheets[user.id]
        await sheet.sync()
        rating = sheet.get_rating(skill)

        if not rating:
            return f'{user.display_name}\'s {skill} rating: **Not yet learning!**'
        
        msg = f'{user.display_name}\'s {skill} rating: **{"Learning!" if rating == "x" else rating}**'
        if progress:
            success = sheet.get_success(skill)
            fail = sheet.get_fail(skill)
            if rating == 'x':
                msg += ' -- [progress: ' + '✓' * (fail + success) + ' ' + '◯ ' * (nature - fail - success) + ']'
            else:
                msg += ' -- [*fail*: ' + '✓' * fail + ' ' + '◯ ' * (rating - fail - 1) + \
                        ' | *success*: ' + '✓' * success + ' ' + '◯ ' * (rating - success) + ']'
        return msg


    async def check_rating(self, skill, channel, user, progress=False):
        if not check_valid_skill(skill):
            return await channel.send(f'{skill} is not a valid skill.')
        
        msg = await self._render_rating(user, skill, progress)
        await message.channel.send(msg)
