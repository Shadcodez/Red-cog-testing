"""Skellige: Yennefer, a funeral, a choice of crown. Original prose."""

NODES = {
    "skellige_dock": {
        "title": "Kaer Trolde, salt and succession",
        "region": "Skellige",
        "banner": "skellige",
        "rest": True,
        "hub": True,
        "unlock": {"velen_done": True},
        "text": (
            "The isles greet you with a fist of weather and a funeral that has not decided who "
            "it is for yet. King Bran is dead. His sons are not ready. Crach an Craite grips "
            "your arm like a man checking you are still made of the same stubbornness.\n\n"
            "\"Yennefer of Vengerberg is in my house,\" he says, \"terrifying the servants and "
            "improving the wine. She said you'd be late. I told her the sea is also late, and "
            "she threatened the sea.\" Ciri's name moves through the hall like a draught."
        ),
        "choices": [
            {"label": "Find Yennefer before she reorganizes the clan", "next": "yen_wake"},
            {"label": "Pay respects. Funerals know things.", "next": "garden"},
            {"label": "Ask about a cave that eats memory", "next": "cave_dreams"},
        ],
    },
    "yen_wake": {
        "title": "Lilac, gooseberries, and a mask",
        "region": "Skellige",
        "banner": "skellige",
        "text": (
            "She is on the balcony, pretending the wind was her idea. Up close the jokes don't "
            "survive. \"Ciri was here for a night. She stole a ship, insulted a god, and left "
            "me a note that said not to follow. I followed.\" The mask of an ermine lies between "
            "you on the table, elven work, warm with old magic.\n\n"
            "\"Help me wake a garden that remembers her, and help these fools not elect a fire. "
            "After that you can tell me why you smell of Novigrad's particular smoke.\""
        ),
        "set": {"met_yen_isles": True},
        "log": "Yennefer is on Skellige. Ciri stole a ship and a head start.",
        "choices": [
            {"label": "The garden under the mountain", "next": "garden"},
            {"label": "Say you've missed her, plainly", "next": "yen_plain"},
        ],
    },
    "yen_plain": {
        "title": "A sentence without armor",
        "region": "Skellige",
        "banner": "romance",
        "text": (
            "Yennefer goes still, which in her is as loud as a shout. \"Don't be sweet at a "
            "funeral. It's in poor taste.\" A beat. \"Say it again when we aren't standing in "
            "another man's grief.\" Her hand finds your wrist, brief as a spark, and the djinn's "
            "old wish sits in the air between you — the one that tied you, the one you have "
            "both wondered whether to cut.\n\n"
            "\"Garden first,\" she says. \"Destiny can wait. It always thinks it can't.\""
        ),
        "set": {"yen_softened": True},
        "choices": [
            {"label": "The garden", "next": "garden"},
        ],
    },
    "garden": {
        "title": "Freya's garden, which does not hurry",
        "region": "Skellige",
        "banner": "skellige",
        "text": (
            "The druids want a king who will not sell the isles to the continent. The garden "
            "wants a key, a tear, and a woman willing to bleed into old soil. Yennefer does it "
            "without theater. Visions rise: Ciri in Lofoten snow, Ciri arguing with an elf named "
            "Avallac'h, Ciri looking back as if she heard you across an ocean.\n\n"
            "After, Yen sits on a stone and does not wipe her face. \"She's alive. Don't ruin "
            "it by looking relieved in public.\" The succession still needs a hand. Hjalmar "
            "offers glory. Cerys offers a future."
        ),
        "set": {"garden_done": True, "ciri_alive_hint": True},
        "choices": [
            {"label": "Back Cerys. A queen who counts boats.", "next": "cerys", "set": {"cerys_queen": True}, "log": "You backed Cerys an Craite."},
            {"label": "Back Hjalmar. The isles love a roar.", "next": "hjalmar", "set": {"hjalmar_king": True}, "log": "You backed Hjalmar an Craite."},
            {"label": "Ask Yen about the last wish. Fade to black after.", "next": "yen_wish", "set": {"yen_romance": True, "yen_softened": True}, "romance": True},
        ],
    },
    "cerys": {
        "title": "A queen with a ledger",
        "region": "Skellige",
        "banner": "skellige",
        "text": (
            "Cerys solves a massacre by refusing to swing first. It is almost unpopular. By "
            "dawn she has a crown and a list, and the list is better than the crown. She clasps "
            "your arm. \"Bring the girl home if home is what she wants. If it isn't, lie to the "
            "emperor. You're good at roads. Be good at doors.\""
        ),
        "choices": [
            {"label": "Speak with Yennefer about the wish", "next": "yen_wish", "set": {"yen_romance": True}, "romance": True, "requires": {"yen_softened": True}},
            {"label": "The cave of dreams, before you sail", "next": "cave_dreams"},
            {"label": "Back to the continent, and Uma", "next": "uma_collect"},
        ],
    },
    "hjalmar": {
        "title": "A king who will do",
        "region": "Skellige",
        "banner": "skellige",
        "text": (
            "Hjalmar wins the way a storm wins: loudly, and with debris. The hall cheers. Cerys "
            "toasts him and starts a list anyway, where he cannot see it. He pounds your back "
            "hard enough to count as diplomacy. \"Ice giant's dead. Your sorceress scares the "
            "skalds. We're even.\"\n\n"
            "Even is not the same as finished."
        ),
        "choices": [
            {"label": "Yennefer is waiting on a djinn", "next": "yen_wish", "set": {"yen_romance": True}, "romance": True, "requires": {"yen_softened": True}},
            {"label": "Collect the cursed man and go", "next": "uma_collect"},
        ],
    },
    "cave_dreams": {
        "title": "The cave that argues with you",
        "region": "Skellige",
        "banner": "skellige",
        "text": (
            "You go in alone because the dream is rude about company. It offers you Blaviken "
            "again, the lesser evil standing in the market with Renfri's shadow measured out in "
            "feet. It offers you Ciri small, holding your hand, asking if witchers get to keep "
            "anything. It offers you a quiet inn that does not exist.\n\n"
            "You walk out with salt on your mouth and no new scars. Yennefer is on the rock "
            "outside, arms folded, not asking what you saw. That is its own kindness."
        ),
        "set": {"dreams_done": True},
        "log": "The cave of dreams had nothing to sell you that you had not already paid.",
        "choices": [
            {"label": "Collect Uma's trail and sail", "next": "uma_collect"},
            {"label": "If you have not yet said the wish, say it", "next": "yen_wish", "requires": {"yen_softened": True, "not:yen_romance": True}, "set": {"yen_romance": True}, "romance": True},
        ],
    },
    "uma_collect": {
        "title": "Ugly cargo",
        "region": "Skellige",
        "banner": "skellige",
        "text": (
            "Uma is exactly as advertised: a curse with a sense of humor, grunting, grabbing, "
            "somehow still a person under the joke. Yennefer circles him once. \"Avallac'h. "
            "I'd bet the coast. We need the laboratory under Kaer Morhen and we need not to "
            "drop him overboard, however tempting the punchline.\"\n\n"
            "Crach lends a ship. The sea, threatened earlier, behaves."
        ),
        "set": {"uma_in_hand": True, "skellige_done": True},
        "log": "Uma is in the hold. The road turns toward Kaer Morhen.",
        "choices": [
            {"label": "Sail for the keep", "next": "kaer_morhen"},
            {"label": "One night in port before the wolf-keep", "next": "skellige_dock"},
        ],
    },
}
