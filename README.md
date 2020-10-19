## What is this?
It's a discord bot that I hacked together very quickly to fit my needs as a dice bot while running Play-By-Post Mouse Guard campaigns. I wanted a bot that had no fluff, could render results using emojis (for snakes, swords, and axes), and could remember rolls for nudging results per game mechanics.

This project is an untested hack. Use at your own risk. If you're reading this, I'm sorry. Fork it and make it good so I can close this repo and just use yours instead.


## Oh god. I know the author of this code. Dear lord, what's broken?
Yeah...  


## I want to run it.
1. [Make a bot account for Discord.](https://discordpy.readthedocs.io/en/latest/discord.html)
2. Install the requirements. Included is a [pipenv](https://docs.pipenv.org/en/latest/) `Pipfile` file (`pipenv install`), but all that is needed is python 3, `discord.py`, `pyyaml`, `gspread`, and `oauth2client`, if you want to install those yourself.
3. Edit the `config.yml` file for your own purposes, and don't commit it to a repository.
4. Run the thing  
`python3 micedice.py --config /path/to/config.yml`

## I want to use it.
    !help                           list commands
    !roll                           initiate the roll builder
    !roll 4                         quick roll dice
    !roll 3 for nature              quick roll dice with reason commentary
    !roll 6 ob 3 for insectrist     quick roll dice against an obstacle with commentary

## TODOs
* More sheets integration
* A better formatted/validated sheet
* Code Quality... seriously... (lol)
* Eventually, I'd want a better roll macro system
* Optional automatic progression tracking


## HACKED TOGETHER: Google Sheets Integration
There's a lot of churn on the steps to set this up, because it's under development - which is really a loose way of saying I have no idea what I'm doing.

Setting up a Google Application... Application  
- Create a project here: https://console.developers.google.com/
- Add/Enable the Google Sheets & Google Drive APIs here: https://console.developers.google.com/apis/
- Create OAUTH2 credentials here: https://console.developers.google.com/apis/credentials
    - Make sure you create credentials for a SERVICE ACCOUNT associated with the app.
- Download the credentials JSON file. This is referenced in the MiceDice configuration.
- Copy the [template sheet](https://docs.google.com/spreadsheets/d/1Ehj1Kc933fx8MCDSob_gUi1sJPIKDA0Yq-TAsKV7gQk/)
- Share the sheet with the service acount email address.
- For each sheet, put the discord user's ID in the top left cell
