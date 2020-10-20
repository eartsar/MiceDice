## What is this?
It's a discord bot that I hacked together very quickly to fit my needs as a dice bot while running Mouse Guard RPG campaigns. I wanted a bot that had no fluff, could render results using emojis (for snakes, swords, and axes), and could do roll flow/math to make the game more approachable for online play.

This project is an untested hack. Use at your own risk. Fork it and make it good so I can close this repo and just use yours instead.


## Oh god. I know the author of this code. Dear lord, what's broken?
Yeah...  


## I want to run it.
1. [Make a bot account for Discord.](https://discordpy.readthedocs.io/en/latest/discord.html)
2. Install the requirements. This project uses [poetry](https://python-poetry.org/), and includes a `pyproject.toml` file (`poetry install`), but all that is needed is python 3, `discord.py`, `PyYAML`, `pygsheets`, and `oauth2client`, if you want to install those yourself.
3. Edit the `config.yml` file, and configure as needed.
4. Run the thing  
`python3 micedice.py --config /path/to/config.yml`

## I want to use it.
    !help                           list commands
    !roll                           starts a roll builder
    !roll 4                         quick roll dice
    !roll 3 for nature              roll dice with reason commentary
    !roll 6 ob 3 for insectrist     roll dice against an obstacle with commentary

## TODOs
* More sheets integration, like progression tracking, and auto-filling roll information
* A better formatted/validated sheet


## Google Sheets Integration (HACKJOB)
There's a lot of churn on the steps to set this up, because I have no idea what I'm doing.

Setting up a Google Application... Application  
- Create a project here: https://console.developers.google.com/
- Add/Enable the Google Sheets & Google Drive APIs here: https://console.developers.google.com/apis/
- Create OAUTH2 credentials here: https://console.developers.google.com/apis/credentials
    - Make sure you create credentials for a SERVICE ACCOUNT associated with the app.
- Download the credentials JSON file. This is referenced in the MiceDice configuration.
- Copy the [template sheet](https://docs.google.com/spreadsheets/d/1Ehj1Kc933fx8MCDSob_gUi1sJPIKDA0Yq-TAsKV7gQk/)
- Share the sheet with the service acount email address.
- For each sheet, put the discord user's ID in the top left cell
