# post2socials
Script om berichten, pipes en afbeeldingen naar Mastodon en/of BlueSky te posten, via de commandline/terminal. Als een afbeelding te groot is, word deze automatisch verkleind.

## Bestanden
* **post2socials.py**, Python script.
* **config.json**, een JSON bestand met de authorisatie gegevens van je Mastodon en BlueSky account.

## Argumenten
* ```-m of --message``` gevolgd door het bericht, tussen aanhalingstekens voor het te plaatsen bericht.
* ```-i of --image``` gevolgd door het pad naar de afbeelding(en), tussen aanhalingstekens en gesepareerd door komma's.
* ```--mastodon``` voor plaatsen op Mastodon
* ```--bluesky``` voor plaatsen op BlueSky

## Gebruiksvoorbeelden
* Post naar Mastodon: ```python script.py -m "Dit is een testbericht" --mastodon```
* Post naar Mastodon, inclusief een afbeelding: ```python script.py -m "Test met afbeelding" -i "pad/naar/afbeelding.jpg" --mastodon```
* Post naar BlueSky: ```python script.py -m "Dit is een testbericht" --bluesky```
* Post naar beide platforms tegelijk: ```python script.py -m "Dit is een testbericht" --mastodon --bluesky```
* Een ander programma output via een pipe plaatsen: ```echo "Automatisch bericht!" | python script.py --mastodon --bluesky```

## Limitaties
* Maximaal 4 afbeeldingen, volgens BlueSky
* Uitvoer van maximaal 300 karakters voor BlueSky, dit kan een probleem zijn met het gebruik van pipes naar BlueSky. Echter is dit nu ondervangen door het dan op te knippen in meerdere stukken. (500 voor Mastodon, 300 voor BlueSky).