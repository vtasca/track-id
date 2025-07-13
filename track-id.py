import typer
import requests

app = typer.Typer()

@app.command()
def search(search_text: str = typer.Argument(..., help="The text to search for")):
    """Search for a track on Bandcamp"""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.6312.86 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


    payload = {
        'fan_id': None,
        'full_page': False,
        'search_filter': '',
        'search_text': search_text
    }

    response = requests.post('https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic',
                headers=headers, json=payload)
    
    if response.status_code == 200:
        print(response.json())
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    typer.run(search)