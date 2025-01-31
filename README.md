# post2socials
Script om berichten, pipes en afbeeldingen naar Mastodon en/of BlueSky te posten, via de commandline/terminal.

## Bestanden
* **post2socials.py**, Python script.
* **config.json**, een JSON bestand met de authorisatie gegevens van je Mastodon en BlueSky account.

## Gebruiksvoorbeelden
* Post naar Mastodon: ```python script.py -m "Dit is een testbericht" --mastodon```
* Post naar Mastodon, inclusief een afbeelding: ```python script.py -m "Test met afbeelding" -i "pad/naar/afbeelding.jpg" --mastodon```
* Post naar BlueSky: ```python script.py -m "Dit is een testbericht" --bluesky```
* Post naar beide platforms tegelijk: ```python script.py -m "Dit is een testbericht" --mastodon --bluesky```
* Een ander programma output via een pipe plaatsen: ```echo "Automatisch bericht!" | python script.py --mastodon --bluesky```
