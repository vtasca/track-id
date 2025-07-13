#!/bin/bash

MP3="$1"
ALBUM_URL="$2"

# Download cover art
uvx yt-dlp --write-thumbnail --skip-download "$ALBUM_URL"

# Find downloaded image
IMG=$(ls *.jpg 2>/dev/null || ls *.webp 2>/dev/null)
if [[ "$IMG" == *.webp ]]; then
  ffmpeg -i "$IMG" cover.jpg
  rm "$IMG"
  IMG="cover.jpg"
fi

# Create temporary output file
TEMP_OUTPUT="temp_${MP3}"

# Embed art with ffmpeg to temporary file
ffmpeg -i "$MP3" -i "$IMG" -map 0 -map 1 -c copy \
  -id3v2_version 3 -metadata:s:v title="Album cover" \
  -metadata:s:v comment="Cover (front)" "$TEMP_OUTPUT"

# Replace original file with modified version
mv "$TEMP_OUTPUT" "$MP3"

# Clean up downloaded image
rm "$IMG"

echo "Embedded album art into $MP3"

