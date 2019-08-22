# MiceDice

----
## What is this?
It's a discord bot that I hacked together very quickly to fit my needs as a dice bot while running Play-By-Post Mouse Guard campaigns. I wanted a bot that had no fluff, could render results using emojis (for snakes, swords, and axes), and could remember rolls for nudging results per game mechanics.

This is largely untested. In fact, if you're reading this, I'm embarrassed. I'm sure there are plenty of bugs I haven't found yet. I actually just thought of one as I typed this out.


----
## Oh god. I know the author of this code. Dear lord, what's broken?
Ouch.  

Okay, fine. I think I forgot to deal with an edge case with rolling zero dice... and I think there's a bug with roll parsing in a specific case... and...

You know your browser has a "back" button, right?

---
## I want to run it.
1. [Make a bot account for Discord.](https://discordpy.readthedocs.io/en/latest/discord.html)
2. Install the requirements. Included is a [pipenv](https://docs.pipenv.org/en/latest/) `Pipfile` file, but all that is needed is python 3, `discord.py`, and `pyyaml` if you want to install those yourself.
3. Edit the `config.yml` file for your own purposes, and don't commit it to a repository.
4. Run the thing  
`python3 micedice.py --config /path/to/config.yml`

----
## I want to use it.
    !help
    !roll <#> [for <reason>]
    !nudge <explode|one|all>
    !last

----
## TODOs
* Fix bugs
* Specify obstacles in rolls optionally `!roll 4ob3 boatcrafting` and automatically display a success/failure/tie result.
* Optionally turn off emoji rendering, and display raw numbers (or dice emojis) instead.
* Use sqlite for saving roll history.
* Point trackers?