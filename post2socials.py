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

def resize_image(image_path):
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        output_path = f"{image_path}_resized.jpg"
        quality = 85
        img.save(output_path, "JPEG", quality=quality)
        
        while os.path.getsize(output_path) > MAX_IMAGE_SIZE and quality > 10:
            quality -= 5
            img.save(output_path, "JPEG", quality=quality)
        
        return output_path

def upload_images_to_bluesky(access_token, image_paths):
    blobs = []
    for image_path in image_paths[:MAX_IMAGES]:  # Max 4 afbeeldingen
        resized_image = resize_image(image_path)
        mime_type, _ = mimetypes.guess_type(resized_image)
        if not mime_type or not mime_type.startswith("image/"):
            print(f"Ongeldig afbeeldingsbestand: {resized_image}")
            continue
        
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": mime_type}
        with open(resized_image, "rb") as image_file:
            response = requests.post(BLUESKY_UPLOAD_URL, headers=headers, data=image_file.read())
        
        if response.status_code == 200:
            blobs.append(response.json().get("blob"))
        else:
            print(f"Fout bij uploaden afbeelding naar Bluesky: {response.status_code}, {response.text}")
    return blobs

def post_to_mastodon(message, image_paths=None):
    media_ids = []
    if image_paths:
        for image_path in image_paths:
            try:
                media = mastodon.media_post(image_path)
                media_ids.append(media['id'])
                print(f"Afbeelding {image_path} succesvol geüpload naar Mastodon!")
            except Exception as e:
                print(f"Fout bij uploaden afbeelding naar Mastodon: {e}")
    mastodon.status_post(message, media_ids=media_ids if media_ids else None)
    print("Bericht geplaatst op Mastodon!")

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
    
    facets = parse_hashtags_and_mentions(message)
    if facets:
        data["record"]["facets"] = facets
    
    if image_paths:
        blobs = upload_images_to_bluesky(access_token, image_paths)
        if blobs:
            data["record"]["embed"] = {
                "$type": "app.bsky.embed.images",
                "images": [{
                    "image": blob,
                    "alt": f"Afbeelding {idx+1} geüpload via script"
                } for idx, blob in enumerate(blobs)]
            }
    
    response = requests.post(BLUESKY_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        print("Bericht succesvol geplaatst op Bluesky!")
    else:
        print(f"Fout bij plaatsen op Bluesky: {response.status_code}, {response.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plaats een bericht op Bluesky en/of Mastodon.")
    parser.add_argument("-m", "--message", type=str, help="Tekstbericht dat geplaatst moet worden.")
    parser.add_argument("-i", "--images", type=str, help="Pad naar afbeeldingen, gescheiden door komma.")
    parser.add_argument("--mastodon", action="store_true", help="Plaats het bericht op Mastodon.")
    parser.add_argument("--bluesky", action="store_true", help="Plaats het bericht op Bluesky.")
    args = parser.parse_args()

    if not sys.stdin.isatty():
        piped_text = sys.stdin.read().strip()
    else:
        piped_text = None

    message = args.message if args.message else piped_text
    image_paths = args.images.split(",") if args.images else []

    if not message:
        print("Fout: Geen bericht opgegeven.")
        sys.exit(1)

    if args.mastodon:
        post_to_mastodon(message, image_paths)
    
    if args.bluesky:
        access_token, did = login_to_bluesky()
        if access_token and did:
            post_to_bluesky(access_token, did, message, image_paths)
        else:
            print("Fout bij inloggen op Bluesky.")

    if not args.mastodon and not args.bluesky:
        print("Fout: Geef --mastodon en/of --bluesky op om het bericht te plaatsen.")