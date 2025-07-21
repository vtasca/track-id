import typer
import requests
import os
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from .id3_tags import ID3_TAG_NAMES

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

@app.command()
def info(file_path: str = typer.Argument(..., help="Path to the MP3 file")):
    """Display information about an MP3 file"""
    
    if not os.path.exists(file_path):
        typer.echo(f"Error: File '{file_path}' does not exist", err=True)
        raise typer.Exit(1)
    
    if not file_path.lower().endswith('.mp3'):
        typer.echo(f"Error: File '{file_path}' is not an MP3 file", err=True)
        raise typer.Exit(1)
    
    try:
        audio = MP3(file_path)
        
        file_size = os.path.getsize(file_path)
        duration_seconds = audio.info.length if audio.info else 0
        
        minutes = int(duration_seconds // 60)
        seconds = int(duration_seconds % 60)
        duration_str = f"{minutes}:{seconds:02d}"
        
        # Get ID3 tags if available
        tags = {}
        try:
            id3 = ID3(file_path)
            for key, value in id3.items():
                if hasattr(value, 'text'):
                    tags[key] = value.text[0] if value.text else ""
        except:
            pass
        
        # Display information
        typer.echo(f"File: {file_path}")
        typer.echo(f"Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
        typer.echo(f"Duration: {duration_str}")
        typer.echo(f"Bitrate: {audio.info.bitrate // 1000} kbps" if audio.info else "Unknown")
        typer.echo(f"Sample Rate: {audio.info.sample_rate} Hz" if audio.info else "Unknown")
        
        if tags:
            typer.echo("\nMetadata:")
            for key, value in tags.items():
                readable_name = ID3_TAG_NAMES.get(key, key)
                typer.echo(f"  {readable_name} ({key}): {value}")
        else:
            typer.echo("\nNo metadata tags found")
            
    except Exception as e:
        typer.echo(f"Error reading MP3 file: {e}", err=True)
        raise typer.Exit(1)

if __name__ == "__main__":
    app()