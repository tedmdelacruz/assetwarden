```
    _    ____ ____  _____ _______        ___    ____  ____  _____ _   _ 
   / \  / ___/ ___|| ____|_   _\ \      / / \  |  _ \|  _ \| ____| \ | |
  / _ \ \___ \___ \|  _|   | |  \ \ /\ / / _ \ | |_) | | | |  _| |  \| |
 / ___ \ ___) |__) | |___  | |   \ V  V / ___ \|  _ <| |_| | |___| |\  |
/_/   \_\____/____/|_____| |_|    \_/\_/_/   \_\_| \_\____/|_____|_| \_|
```

# assetwarden

Monitoring webpage assets, particularly JavaScript files, is highly useful in cybersecurity research. This enables security researchers to quickly find new API endpoints, exposed secrets, and even website features that are not yet available to the public.

However, there are many challenges in monitoring webpage assets. Some of which are:
- Dynamically loaded JS files that are not immediately loaded in the DOM tree.
- Unpredictable JS filenames that contain hashes (ex. `app.94d7d0ecf48110ba.js`).
- JS assets are sometimes loaded behind authenticated pages.

`assetwarden` is a simple asset monitoring framework that aims to tackle these issues.

## Features
- Easily configurable via `config.yaml`
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

## TODO
- [ ] Allow setting of custom authentication headers and cookies
- [ ] Add support for Slack notifications