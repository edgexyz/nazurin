# Poipiku

<https://poipiku.com/>

## Configuration

### POIPIKU_TOKEN

:material-lightbulb-on: Optional

Value of the `POIPIKU_LK` cookie from a logged-in browser session.

- **Without `POIPIKU_TOKEN`**: Works for public, R-15/warning, and standard age-confirmation (R-18) posts using public display images (`_640.jpg` JPEG previews). Posts gated by login, follower/X restrictions, passwords, or R18+ Poipass verification are not accessible without the required credentials.
- **With `POIPIKU_TOKEN`**:
  - Unlocks original images (signed CDN URLs preserving original PNG/JPEG/GIF/WebP format) via Poipiku's detail endpoint.
  - Accesses login-only and follower-restricted posts that your account has permission to view.
  - Raises an error if `POIPIKU_TOKEN` is invalid or expired.

## Customizing Storage Path & File Name

For more information, refer to [Customizing Storage Path & File Name](./index.md/#customizing-storage-path--file-name).

### POIPIKU_FILE_PATH

:material-lightbulb-on: Optional, defaults to `Poipiku`

Storage path for downloaded images.

### POIPIKU_FILE_NAME

:material-lightbulb-on: Optional, defaults to `{id}_{index} - {user[name]}({user[id]})`

File name for downloaded images.

### Available Variables

_Only common used ones are listed._

```json
{
  "id": "Post ID",
  "url": "Post URL",
  "category": "Post category (e.g. できた, らくがき)",
  "description": "Post description / caption",
  "tags": ["Tag 1", "Tag 2"],
  "user": {
    "id": "Creator user ID",
    "name": "Creator display name",
    "profile": "Creator profile description",
    "avatar": "Creator avatar URL",
    "url": "Creator box URL",
    "posts_num": "Number of posts (ポイポイ)",
    "is_following": false
  },
  "original": "Whether original images were fetched (true when POIPIKU_TOKEN is set)",
  "filename": "Original file name stem, without extension",
  "index": "Image index (0-based)",
  "extension": "Extension, with leading dot"
}
```
