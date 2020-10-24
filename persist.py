import aiosqlite


class DatabaseManager():
    def __init__(self, sqlite3_file):
        '''Given a sheets URL, and a list of player discord IDs, return a
        dictionary of discord_id --> GoogleBackedSheet object'''
        self.dbpath = sqlite3_file
    

    async def initialize(self):
        async with aiosqlite.connect(self.dbpath) as db:
            print("Connecting to SQLITE database...")
            sql = 'CREATE TABLE IF NOT EXISTS PLAYER_SHEETS (user_id int, sheets_url varchar(255))'
            print('> ' + sql)
            await db.execute(sql)
            sql = "SELECT name FROM sqlite_master WHERE type ='table' AND name NOT LIKE 'sqlite_%'";
            cursor = await db.execute(sql)
            rows = await cursor.fetchall()
            print(str(rows))

    
    async def _get_profile_urls(self, user):
        urls = []
        async with aiosqlite.connect(self.dbpath) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(f'SELECT sheets_url FROM PLAYER_SHEETS WHERE user_id = {user.id}') as cursor:
                urls = [row['sheets_url'] for row in await cursor.fetchall()]
        return urls


    async def get_profiles(self, user):
        return self._get_profile_urls(user)


    async def add_profile(self, user, url):
        profile_urls = await self._get_profile_urls(user)

        if url in profile_urls:
            return
        
        async with aiosqlite.connect(self.dbpath) as db:
            await db.execute(f"INSERT INTO PLAYER_SHEETS (user_id, sheets_url) VALUES ({user.id}, '{url}')")
            await db.commit()


    async def delete_profile(self, user, url):
        async with aiosqlite.connect(self.dbpath) as db:
            sql = f"DELETE FROM PLAYER_SHEETS WHERE user_id = {user.id} AND sheets_url = '{url}'"
            print('> ' + sql)
            await db.execute(sql)


