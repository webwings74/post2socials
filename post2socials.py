import json
import sys
import argparse
import re
import mimetypes
import os
from mastodon import Mastodon
import requests
from datetime import datetime, timezone
from PIL import Image

# Config-bestanden
CONFIG_FILE = "config-webwings.json"

# Maximale afbeeldingsgrootte voor Bluesky (976.56KB ~ 1MB)
MAX_IMAGE_SIZE = 976 * 1024
MAX_IMAGES = 4  # Bluesky ondersteunt maximaal 4 afbeeldingen per post

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
BLUESKY_UPLOAD_URL = "https://bsky.social/xrpc/com.atproto.repo.uploadBlob"
BLUESKY_DID_LOOKUP_URL = "https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle={}"

def login_to_bluesky():
    payload = {"identifier": config.get("bluesky_handle"), "password": config.get("bluesky_password")}
    response = requests.post(BLUESKY_LOGIN_URL, json=payload)
    if response.status_code == 200:
        data = response.json()
        return data.get("accessJwt"), data.get("did")
    return None, None

def get_did_for_handle(handle):
    if not handle.endswith(".bsky.social"):
        handle = f"{handle}.bsky.social"
    response = requests.get(BLUESKY_DID_LOOKUP_URL.format(handle))
    if response.status_code == 200:
        return response.json().get("did")
    return None

def parse_hashtags_mentions_urls(message):
    facets = []
    if not message:
        return None
    
    for match in re.finditer(r"(@[\w.-]+|#[\w]+|https?://\S+)", message):
        match_text = match.group(0)
        start, end = match.span()
        
        if match_text.startswith("#"):
            facet_type = "app.bsky.richtext.facet#tag"
            facet_data = {"$type": facet_type, "tag": match_text[1:]}
        elif match_text.startswith("@"):  
            did = get_did_for_handle(match_text[1:])
            facet_type = "app.bsky.richtext.facet#mention" if did else None
            facet_data = {"$type": facet_type, "did": did} if did else None
        elif match_text.startswith("http"):
            facet_type = "app.bsky.richtext.facet#link"
            facet_data = {"$type": facet_type, "uri": match_text}
        else:
            continue
        
        if facet_data:
            facets.append({
                "index": {"byteStart": start, "byteEnd": end},
                "features": [facet_data]
            })
    
    return facets if facets else None

def post_to_mastodon(message, image_paths=None):
    media_ids = []
    
    if image_paths:
        for image_path in image_paths:
            try:
                media = mastodon.media_post(image_path, description="Afbeelding bij post")
                media_ids.append(media["id"])
            except Exception as e:
                print(f"Fout bij uploaden van afbeelding {image_path}: {e}")
    
    try:
        mastodon.status_post(message, media_ids=media_ids)
        print("Bericht succesvol geplaatst op Mastodon!")
    except Exception as e:
        print(f"Fout bij plaatsen op Mastodon: {e}")

def post_to_bluesky(access_token, did, message, image_paths=None):
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    data = {
        "repo": did,
        "collection": "app.bsky.feed.post",
        "record": {
            "text": message,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
    }
    
    facets = parse_hashtags_mentions_urls(message)
    if facets:
        data["record"]["facets"] = facets
    
    response = requests.post(BLUESKY_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        print("Bericht succesvol geplaatst op Bluesky!")
    else:
        print(f"Fout bij plaatsen op Bluesky: {response.status_code}, {response.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plaats een bericht op Bluesky en/of Mastodon.")
    parser.add_argument("-m", "--message", type=str, required=True, help="Tekstbericht dat geplaatst moet worden.")
    parser.add_argument("-i", "--images", type=str, help="Pad naar afbeeldingen, gescheiden door komma.")
    parser.add_argument("--mastodon", action="store_true", help="Plaats het bericht op Mastodon.")
    parser.add_argument("--bluesky", action="store_true", help="Plaats het bericht op Bluesky.")
    args = parser.parse_args()
    
    image_paths = args.images.split(",") if args.images else []
    
    if args.mastodon:
        post_to_mastodon(args.message, image_paths)
    
    if args.bluesky:
        access_token, did = login_to_bluesky()
        if access_token and did:
            post_to_bluesky(access_token, did, args.message, image_paths)
        else:
            print("Fout bij inloggen op Bluesky.")
