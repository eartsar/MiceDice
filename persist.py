import aiosqlite


class DatabaseManager():
    def __init__(self, sqlite3_file):
        '''Given a sheets URL, and a list of player discord IDs, return a
        dictionary of discord_id --> GoogleBackedSheet object'''
        self.dbpath = sqlite3_file
    

    async def initialize(self):
        async with aiosqlite.connect(self.dbpath) as db:
            print("Connecting to and preparing SQLITE database...")
            await db.execute('CREATE TABLE IF NOT EXISTS PLAYER_SHEETS (user_id int, sheets_key varchar(255), current boolean)')
            print("Done.")

    
    async def _get_profile_keys(self, user):
        urls = []
        async with aiosqlite.connect(self.dbpath) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(f'SELECT sheets_key FROM PLAYER_SHEETS WHERE user_id = {user.id}') as cursor:
                urls = [row['sheets_key'] for row in await cursor.fetchall()]
        return urls


    async def get_profiles(self, user):
        return self._get_profile_urls(user)


    async def add_profile(self, user, key):
        profile_keys = await self._get_profile_keys(user)

        if key in profile_keys:
            return False
        
        async with aiosqlite.connect(self.dbpath) as db:
            await db.execute(f"INSERT INTO PLAYER_SHEETS (user_id, sheets_key) VALUES ({user.id}, '{key}')")
            await db.commit()
        return True


    async def delete_profile(self, user, key):
        async with aiosqlite.connect(self.dbpath) as db:
            await db.execute(f"DELETE FROM PLAYER_SHEETS WHERE user_id = {user.id} AND sheets_key = '{key}'")
            await db.commit()
            return db.total_changes > 0


    async def get_current(self, user):
        async with aiosqlite.connect(self.dbpath) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(f'SELECT sheets_key FROM PLAYER_SHEETS WHERE user_id = {user.id} AND current = TRUE') as cursor:
                return (await cursor.fetchone())['sheets_key']


    async def update_current(self, user, key):
        async with aiosqlite.connect(self.dbpath) as db:
            await db.execute(f"UPDATE PLAYER_SHEETS SET current = FALSE WHERE user_id = {user.id} AND sheets_key = '{key}' AND current = TRUE")
            await db.commit()
            await db.execute(f"UPDATE PLAYER_SHEETS SET current = TRUE WHERE user_id = {user.id} AND sheets_key = '{key}'")
            await db.commit()


