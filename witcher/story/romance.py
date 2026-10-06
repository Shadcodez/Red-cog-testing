"""Romance scenes. Every instance fades to black and stays PG-13. Original prose."""

NODES = {
    "keira_night": {
        "title": "Keira, the door shuts",
        "region": "Velen",
        "banner": "romance",
        "romance": True,
        "text": (
            "Keira walks you to the tower door and stops with her hand on the latch. The swamp "
            "is loud. She is not. \"I'm fond of evenings that don't become reports,\" she says. "
            "She kisses you once, quick as a dare, and the door closes.\n\n"
            "Fade to black.\n\n"
            "Morning is tea, a blanket folded with military precision, and Keira already dressed "
            "for the road. \"Don't look at me as if this fixes the continent. It fixed the "
            "evening.\" If you ask her to ride for Kaer Morhen instead of a king's pardon, she "
            "will swear, then pack. If you don't, she still smiles. Smiles are cheap. Directions aren't."
        ),
        "choices": [
            {"label": "Ask her to the keep at dawn", "next": "keira_safe", "set": {"keira_to_morhen": True}},
            {"label": "Leave it as an evening. Take the Uma road.", "next": "uma_hint", "set": {"keira_evening_only": True}},
        ],
    },
    "triss_dock": {
        "title": "The lighthouse door",
        "region": "Novigrad",
        "banner": "romance",
        "romance": True,
        "text": (
            "You ask her on the dock, badly, which is the only way you ask for anything that "
            "isn't a contract. Triss misses the Kovir tide on purpose. The lighthouse keeper "
            "owes Dandelion money and therefore owes you a key. She takes your hand at the "
            "threshold, says your name like she means to keep it, and shuts the door.\n\n"
            "Fade to black.\n\n"
            "Dawn smells of tar and cinnamon. Her hair is a lost cause and her laugh isn't. "
            "\"If your sorceress asks,\" she says, pouring tea, \"tell her the truth. I'm done "
            "being the paragraph someone skips.\" The hunters are still out there. So is the road."
        ),
        "set": {"triss_stayed": True},
        "log": "Triss stayed. The lighthouse keeps the rest.",
        "choices": [
            {"label": "Back to the city, and Whoreson", "next": "whoreson"},
            {"label": "If the bridge is already behind you, sail", "next": "skellige_dock", "requires": {"saved_dandelion": True}},
        ],
    },
    "yen_wish": {
        "title": "The last wish, then the door",
        "region": "Skellige",
        "banner": "romance",
        "romance": True,
        "text": (
            "You find a djinn because Yennefer does not believe in metaphors when a literal "
            "monster will do. The fight is embarrassing and wet. After, on a shore that has "
            "the decency to be empty, you tell her the wish can be cut. That the tie was never "
            "the reason you came back. That the books can call it destiny if they need a shorter "
            "word than choice.\n\n"
            "She kisses you once to shut you up. Then she takes your hand, and the cottage door "
            "on the cliff closes.\n\n"
            "Fade to black.\n\n"
            "In the morning the wish is gone. She is carding a hand through your hair and "
            "threatening to turn you into the unicorn from Lambert's joke if you ever wish for "
            "her again. The habit of her isn't gone at all."
        ),
        "set": {"yen_wish_broken": True, "yen_stayed": True},
        "log": "The last wish is broken. Yennefer stays because she decides to.",
        "choices": [
            {"label": "Collect Uma and sail for the keep", "next": "uma_collect"},
            {"label": "The cave, if you haven't already lost an afternoon to it", "next": "cave_dreams", "requires": {"not:dreams_done": True}},
        ],
    },
    "shani_night": {
        "title": "Oxenfurt, the latch clicks",
        "region": "Hearts of Stone",
        "banner": "romance",
        "romance": True,
        "text": (
            "Shani walks you as far as her lodging and stops under a lamp that has seen better "
            "students. She is funny about the ghost who wore your face at the wedding. \"He "
            "danced better. Don't let it ruin you.\" Then she kisses your cheek, says this is "
            "a chapter and not a life, and closes the door.\n\n"
            "Fade to black.\n\n"
            "Morning is bread, a note about the painted rose, and Shani already late for a "
            "lecture. \"Try not to die for a riddle,\" she says at the gate. \"It's an "
            "embarrassing cause of death.\" Oxenfurt owns her next year. You own a pact with "
            "a man who is mostly small print."
        ),
        "log": "An evening with Shani, and nothing the morning needs to narrate.",
        "choices": [
            {"label": "Iris's painted house", "next": "painted_gate"},
        ],
    },
    "syanna_night": {
        "title": "Syanna, the terrace door",
        "region": "Blood and Wine",
        "banner": "romance",
        "romance": True,
        "text": (
            "Syanna wants to be chosen without being pardoned. You can give her the first. "
            "The second isn't yours. On the terrace she laughs, drops the bandit act for as "
            "long as a toast takes, and kisses you like a woman editing her own fairy tale. "
            "Then she sends the servants out and shuts the door.\n\n"
            "Fade to black.\n\n"
            "Breakfast is indecently pretty, which she treats as an insult. \"If you give me "
            "that stupid childhood ribbon, I'll wear it. If you don't, I'll still walk into "
            "the book. I'm done waiting to be invited to my own story.\""
        ),
        "log": "Syanna had the evening. The duchy can wait until morning.",
        "choices": [
            {"label": "Give her the ribbon with breakfast", "next": "fables_gate", "set": {"gave_ribbon": True}},
            {"label": "Keep the morning practical", "next": "fables_gate"},
        ],
    },
    "both_fail": {
        "title": "Two sorceresses, one bad plan",
        "region": "Kaer Morhen",
        "banner": "romance",
        "romance": True,
        "text": (
            "The invitation is delivered with the polite malice of people who have compared "
            "notes. Triss pours. Yennefer does not drink. They let you understand, slowly, that "
            "you are not walking into a song. You are walking into an audit.\n\n"
            "Nobody locks a door. The scene does not go anywhere a younger man might have "
            "hoped. It becomes a precise conversation about being chosen second, conducted "
            "over tea, and then it fades to black on the awkward silence rather than on anything "
            "else.\n\n"
            "Fade to black.\n\n"
            "Dandelion, who definitely listened in the hall, will later invent a much "
            "worse version. He is wrong.\n\n"
            "They leave you the kettle and the lesson. The lesson is the expensive part."
        ),
        "set": {"both_caught": True},
        "log": "Triss and Yennefer compared notes. The romance paths both close.",
        "choices": [
            {"label": "The laboratory. Some curses are simpler.", "next": "uma_lift"},
        ],
    },
}
