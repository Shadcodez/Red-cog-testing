from __future__ import annotations

import discord

JSON_EMOJI = "📦"

DEFAULT_EMBED_TITLE = "Welcome to the embed builder"

DEFAULT_EMBED_DESCRIPTION = """
- Use the grey buttons to edit the various components of the embed. Use the red clear button to nullify all of the embed's components.
- You can add or remove fields with the green and red buttons located just under the grey buttons.
- Get the embed's Python code using the "Get Python" code. This can be used for debugs or for your own code. Get the embed's JSON via the "Get JSON" button. This can be used to store your embeds for shorthand, or to use elsewhere.
- There are two buttons which can modify the embed using JSON:
    - **replace** - Replaces all the embed's current JSON data with the uploaded data.
    - **update** - Replaces only the specified keys.
- You can convert this embed directly into a modern Discord UI Container with the "To Container" button.
- Once you're done, you may send the embed to a desired channel using the dropdown.
- You may also pass options directly through the command, for example: `[p]embedcreate title: My Embed colour: red builder: no`
- The following options are supported:
  - **title** - Embed title.
  - **description** - Embed description.
  - **colour/color** - A valid colour or hex code.
  - **url** - A valid URL for the embed's title hyperlink.
  - **image** - A valid URL for the embed's image.
  - **thumbnail** - A valid URL for the embed's thumbnail.
  - **author_name** - The name of the embed's author.
  - **author_url** - A valid URL for the author's hyperlink.
  - **author_icon_url** - A valid URL for the author's icon image.
  - **footer_name** - Text for the footer.
  - **footer_icon_url** - A valid URL for the footer's icon image.
  - **builder** - Whether this help menu appears along with the constructor buttons. Defaults to true.
  - **source** - An existing message to use its embed. Can be a link or message ID.
  - **content** - The text sent outside of the message.
""".strip()

DEFAULT_CONTAINER_TITLE = "Welcome to the Container Builder"

DEFAULT_CONTAINER_TEXT = """
### Container tools
This is a Components V2 container, not an embed. Discord cannot show normal message text with it.
- **Accent** sets the side colour. **Spoiler** blurs the whole container. **Clear** wipes it. **To Embed** converts it back.
- **+ Text** adds a markdown block. Headers, bold, lists, and code work.
- **+ Thumb Sec** puts up to 3 text blocks beside an image. **+ Btn Sec** puts text beside a link button.
- **+ Divider** is a horizontal line only. **+ Media** adds a gallery image. **+ Link Btn** adds a link, with an optional emoji.
- **+ File** asks you to upload a file. It is attached to the message and shown as a file card.
- **Edit / Move** opens a block to change it, moves it up or down, or removes one gallery image.
- **- Remove** deletes a whole block. **Export** gets Python, JSON, or replaces the container from JSON.
- The channel menu posts a copy without these buttons.
""".strip()


def shorten_by(s: str, /, length: int) -> str:
    if len(s) > length:
        return s[: length - 1] + "…"
    return s
