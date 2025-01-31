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
import grapheme  # Voor het correct tellen van Unicode-graphemes

# Config-bestanden
CONFIG_FILE = "config-webwings.json"

# Maximale afbeeldingsgrootte voor Bluesky (976.56KB ~ 1MB)
MAX_IMAGE_SIZE = 976 * 1024
MAX_IMAGES = 4  # Bluesky ondersteunt maximaal 4 afbeeldingen per post

# Maximale berichtlengte voor Mastodon en Bluesky
MASTODON_MAX_LENGTH = 500  # Mastodon heeft een limiet van 500 tekens
BLUESKY_MAX_LENGTH = 300   # Bluesky heeft een limiet van 300 tekens

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

def resize_image(image_path):
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        temp_path = f"{image_path}_resized.jpg"
        quality = 85
        img.save(temp_path, "JPEG", quality=quality)
        
        while os.path.getsize(temp_path) > MAX_IMAGE_SIZE and quality > 10:
            quality -= 5
            img.save(temp_path, "JPEG", quality=quality)
        
        return temp_path if os.path.getsize(temp_path) <= MAX_IMAGE_SIZE else None

def upload_image_to_bluesky(access_token, image_path):
    resized_path = resize_image(image_path)
    if not resized_path:
        print(f"Afbeelding {image_path} is te groot en kon niet verkleind worden.")
        return None
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": mimetypes.guess_type(resized_path)[0] or "image/jpeg"
    }
    
    with open(resized_path, "rb") as img_file:
        response = requests.post(BLUESKY_UPLOAD_URL, headers=headers, data=img_file.read())
    
    os.remove(resized_path)  # Verwijder tijdelijk bestand
    
    if response.status_code == 200:
        return response.json().get("blob")
    else:
        print(f"Fout bij uploaden afbeelding naar Bluesky: {response.status_code}, {response.text}")
        return None

def split_message(message, max_length):
    """Splits een bericht in delen van maximaal max_length tekens, inclusief paginanummers (indien nodig)."""
    parts = []
    total_parts = (grapheme.length(message) // (max_length - 10)) + 1  # Reserveer ruimte voor paginanummers
    
    # Als het bericht niet gesplitst hoeft te worden, retourneer het originele bericht
    if total_parts == 1:
        return [message]
    
    for i in range(total_parts):
        start = i * (max_length - 10)  # Reserveer ruimte voor paginanummers
        end = start + (max_length - 10)
        part = grapheme.slice(message, start, end)
        
        # Voeg paginanummer toe
        part_with_number = f"({i + 1}/{total_parts}) {part}"
        
        # Controleer of het paginanummer de limiet overschrijdt
        if grapheme.length(part_with_number) > max_length:
            part = grapheme.slice(part, 0, max_length - grapheme.length(f"({i + 1}/{total_parts}) "))
            part_with_number = f"({i + 1}/{total_parts}) {part}"
        
        parts.append(part_with_number)
    
    return parts

def post_to_mastodon(message, image_paths=None):
    media_ids = []
    
    if image_paths:
        for image_path in image_paths:
            try:
                media = mastodon.media_post(image_path, description="Afbeelding bij post")
                media_ids.append(media["id"])
            except Exception as e:
                print(f"Fout bij uploaden van afbeelding {image_path}: {e}")
    
    # Splits het bericht als het te lang is
    message_parts = split_message(message, MASTODON_MAX_LENGTH)
    
    try:
        # Post het eerste deel van het bericht
        status = mastodon.status_post(message_parts[0], media_ids=media_ids)
        print("Eerste deel van het bericht succesvol geplaatst op Mastodon!")
        
        # Post de rest van de delen als een thread
        for part in message_parts[1:]:
            status = mastodon.status_post(part, in_reply_to_id=status["id"])
            print("Volgend deel van het bericht succesvol geplaatst op Mastodon!")
    except Exception as e:
        print(f"Fout bij plaatsen op Mastodon: {e}")

def post_to_bluesky(access_token, did, message, image_paths=None):
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    # Splits het bericht als het te lang is
    message_parts = split_message(message, BLUESKY_MAX_LENGTH)
    
    # Post het eerste deel van het bericht
    data = {
        "repo": did,
        "collection": "app.bsky.feed.post",
        "record": {
            "text": message_parts[0],
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
    }
    
    facets = parse_hashtags_mentions_urls(message_parts[0])
    if facets:
        data["record"]["facets"] = facets
    
    image_blobs = []
    if image_paths:
        for image_path in image_paths:
            blob = upload_image_to_bluesky(access_token, image_path)
            if blob:
                image_blobs.append({"image": blob, "alt": "Afbeelding"})
    
    if image_blobs:
        data["record"]["embed"] = {"$type": "app.bsky.embed.images", "images": image_blobs}
    
    response = requests.post(BLUESKY_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        print("Eerste deel van het bericht succesvol geplaatst op Bluesky!")
        parent_post_uri = response.json().get("uri")
        parent_post_cid = response.json().get("cid")  # Haal de CID op uit het antwoord
        
        # Post de rest van de delen als een thread
        for part in message_parts[1:]:
            data = {
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": {
                    "text": part,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "reply": {
                        "parent": {"uri": parent_post_uri, "cid": parent_post_cid},
                        "root": {"uri": parent_post_uri, "cid": parent_post_cid}
                    }
                }
            }
            response = requests.post(BLUESKY_API_URL, headers=headers, json=data)
            if response.status_code == 200:
                print("Volgend deel van het bericht succesvol geplaatst op Bluesky!")
            else:
                print(f"Fout bij plaatsen van volgend deel op Bluesky: {response.status_code}, {response.text}")
    else:
        print(f"Fout bij plaatsen op Bluesky: {response.status_code}, {response.text}")
        
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plaats een bericht op Bluesky en/of Mastodon.")
    parser.add_argument("-m", "--message", type=str, help="Tekstbericht dat geplaatst moet worden.")
    parser.add_argument("-i", "--images", type=str, help="Pad naar afbeeldingen, gescheiden door komma.")
    parser.add_argument("--mastodon", action="store_true", help="Plaats het bericht op Mastodon.")
    parser.add_argument("--bluesky", action="store_true", help="Plaats het bericht op Bluesky.")
    args = parser.parse_args()
    
    message = args.message if args.message else sys.stdin.read().strip()
    image_paths = args.images.split(",") if args.images else []
    
    if args.mastodon:
        post_to_mastodon(message, image_paths)
    
    if args.bluesky:
        access_token, did = login_to_bluesky()
        if access_token and did:
            post_to_bluesky(access_token, did, message, image_paths)
        else:
            print("Fout bij inloggen op Bluesky.")