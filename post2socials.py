import json
import sys
import argparse
import re
from mastodon import Mastodon
import requests
from datetime import datetime, timezone

# Config-bestanden
CONFIG_FILE = "config-webwings.json"

def load_config():
    with open(CONFIG_FILE, "r") as config_file:
        return json.load(config_file)

config = load_config()

# Mastodon setup
mastodon = Mastodon(
    access_token=config.get("mastodon_access_token"),
    api_base_url=config.get("mastodon_api_base_url")
)

# Bluesky setup
BLUESKY_API_URL = "https://bsky.social/xrpc/com.atproto.repo.createRecord"
BLUESKY_LOGIN_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"

def login_to_bluesky():
    payload = {"identifier": config.get("bluesky_handle"), "password": config.get("bluesky_password")}
    response = requests.post(BLUESKY_LOGIN_URL, json=payload)
    if response.status_code == 200:
        data = response.json()
        return data.get("accessJwt"), data.get("did")
    return None, None

def parse_hashtags_and_mentions(message):
    facets = []
    if not message:
        return None
    
    for match in re.finditer(r"(@[\w.-]+|#[\w]+)", message):
        match_text = match.group(0)
        start, end = match.span()
        
        if match_text.startswith("#"):
            facet_type = "app.bsky.richtext.facet#tag"
            facet_data = {"$type": facet_type, "tag": match_text[1:]}
        elif match_text.startswith("@"):  
            facet_type = "app.bsky.richtext.facet#mention"
            facet_data = {"$type": facet_type, "did": match_text[1:]}
        else:
            continue
        
        facets.append({
            "index": {"byteStart": start, "byteEnd": end},
            "features": [facet_data]
        })
    return facets if facets else None

def post_to_mastodon(message, image_path=None):
    media_id = None
    if image_path:
        try:
            media = mastodon.media_post(image_path)
            media_id = media['id']
            print("Afbeelding succesvol geüpload naar Mastodon!")
        except Exception as e:
            print(f"Fout bij uploaden afbeelding naar Mastodon: {e}")
    mastodon.status_post(message, media_ids=[media_id] if media_id else None)
    print("Bericht geplaatst op Mastodon!")

def post_to_bluesky(access_token, did, message):
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    data = {
        "repo": did,
        "collection": "app.bsky.feed.post",
        "record": {
            "text": message,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
    }
    
    facets = parse_hashtags_and_mentions(message)
    if facets:
        data["record"]["facets"] = facets
    
    response = requests.post(BLUESKY_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        print("Bericht succesvol geplaatst op Bluesky!")
    else:
        print(f"Fout bij plaatsen op Bluesky: {response.status_code}, {response.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plaats een bericht op Bluesky en/of Mastodon.")
    parser.add_argument("-m", "--message", type=str, help="Tekstbericht dat geplaatst moet worden.")
    parser.add_argument("-i", "--image", type=str, help="Pad naar afbeelding (optioneel).")
    parser.add_argument("--mastodon", action="store_true", help="Plaats het bericht op Mastodon.")
    parser.add_argument("--bluesky", action="store_true", help="Plaats het bericht op Bluesky.")
    args = parser.parse_args()

    if not sys.stdin.isatty():
        piped_text = sys.stdin.read().strip()
    else:
        piped_text = None

    message = args.message if args.message else piped_text

    if not message:
        print("Fout: Geen bericht opgegeven.")
        sys.exit(1)

    if args.mastodon:
        post_to_mastodon(message, args.image)
    
    if args.bluesky:
        access_token, did = login_to_bluesky()
        if access_token and did:
            post_to_bluesky(access_token, did, message)
        else:
            print("Fout bij inloggen op Bluesky.")

    if not args.mastodon and not args.bluesky:
        print("Fout: Geef --mastodon en/of --bluesky op om het bericht te plaatsen.")
