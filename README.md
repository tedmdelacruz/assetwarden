```
    _    ____ ____  _____ _______        ___    ____  ____  _____ _   _ 
   / \  / ___/ ___|| ____|_   _\ \      / / \  |  _ \|  _ \| ____| \ | |
  / _ \ \___ \___ \|  _|   | |  \ \ /\ / / _ \ | |_) | | | |  _| |  \| |
 / ___ \ ___) |__) | |___  | |   \ V  V / ___ \|  _ <| |_| | |___| |\  |
/_/   \_\____/____/|_____| |_|    \_/\_/_/   \_\_| \_\____/|_____|_| \_|
```

# assetwarden

Monitoring webpage assets, particularly JavaScript files, is highly useful in cybersecurity research. This enables security researchers to quickly find new API endpoints, exposed secrets, and even website features not yet available to the public.

`assetwarden` is a simple utility script that monitors JavaScript files of a website for changes.

## Features
- Easily configurable
- Multithreading support
- Discord notifications
- Automatic diff generation

## Usage

### Configure the script
- `save_path` - Directory of monitored files and the generated diffs
- `enable_multithreading` - Enable or disable multithreading
- `discord_webhook_url` - [Discord webhook URL](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks)

Run the following:

```sh
python assetwarden.py
```