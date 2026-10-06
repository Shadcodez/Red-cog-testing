"""White Orchard and the Vizima audience. Original prose."""

NODES = {
    "crossroads": {
        "title": "A crossroads with a bad reputation",
        "region": "White Orchard",
        "banner": "orchard",
        "rest": True,
        "hub": True,
        "text": (
            "The inn sign creaks like a guilty man. Someone has chalked a griffin over the door "
            "and then tried to wipe it off, which only made the wings bigger. Vesemir is by the "
            "horse trough, oiling a blade that has outlived three kings. He does not look up.\n\n"
            "\"Yen was here,\" he says. \"Left in a hurry, which is her way of saying she loves "
            "a problem. The Nilfgaardians want the beast dead before it eats another clerk. "
            "We want the woman who was asking about Ciri. Those are not the same job. They "
            "only share a road.\"\n\n"
            "Roach snorts, unimpressed by destiny. Your purse is light. Your medallion is quiet. "
            "For now."
        ),
        "choices": [
            {"label": "Take a table and listen", "next": "orchard_inn"},
            {"label": "Ask Vesemir what Yen actually said", "next": "yen_hint", "log": "Yennefer passed through White Orchard hunting the same girl."},
            {"label": "Ride for the Nilfgaardian camp", "next": "nilf_camp"},
            {"label": "Read the notice board before someone else does", "next": "orchard_board"},
            {"label": "Sit the night out with a book", "next": "book_fire"},
        ],
    },
    "yen_hint": {
        "title": "What the sorceress left behind",
        "region": "White Orchard",
        "banner": "orchard",
        "text": (
            "Vesemir turns the sword so the fire lives along the fuller. \"She didn't plead. "
            "Yen doesn't plead. She said Ciri ran from the Hunt, and that if we found the girl "
            "first we might still get to pretend this was a family matter.\" He almost smiles. "
            "\"Book of yours used to say destiny is a blade with two edges. I've always thought "
            "it was a bill. Comes due whether you read it or not.\"\n\n"
            "He nods at the swamp. \"Griffin first. Dead witchers don't rescue anyone.\""
        ),
        "choices": [
            {"label": "Back to the inn", "next": "orchard_inn"},
            {"label": "Straight to the garrison", "next": "nilf_camp"},
        ],
    },
    "orchard_inn": {
        "title": "The White Orchard inn",
        "region": "White Orchard",
        "banner": "inn",
        "rest": True,
        "text": (
            "The ale is mostly river. The stew is mostly rumor. A merchant swears the griffin "
            "took his partner and left the boots, which is either grief or a very committed lie. "
            "The barmaid says a dark-haired woman paid in Temerian coin and asked who had seen "
            "a girl with ashen hair. Nobody had. Everybody had an opinion.\n\n"
            "In the corner, two soldiers argue about whether Nilfgaard burns libraries out of "
            "policy or only when the books answer back. You eat. The medallion stays still. "
            "That will not last."
        ),
        "choices": [
            {"label": "Buy a round and loosen tongues", "next": "griffin_rumor", "items": {"crowns": -5}, "log": "The griffin nests in the old watchtower, and it is not alone."},
            {"label": "Skip the ale. Find the nest.", "next": "griffin_rumor"},
            {"label": "Ask if anyone plays cards worth the name", "next": "gwent_orchard"},
        ],
    },
    "orchard_board": {
        "title": "Notice board, mud, and a noonwraith",
        "region": "White Orchard",
        "banner": "orchard",
        "text": (
            "Three notices, all damp. A devil in the well. A deserter. A request for five "
            "bushels of honesty, which the village does not stock. The well-contract is written "
            "in a careful hand: a bride who hanged herself rather than marry a man her father "
            "picked. Classic noonwraith. Tragic, local, and not your war.\n\n"
            "You can still take it. Witchers who only chase legends starve between legends."
        ),
        "choices": [
            {"label": "Take the well contract", "next": "devil_well", "log": "Contract: the devil by the well."},
            {"label": "Leave it. Griffins pay better.", "next": "orchard_inn"},
        ],
    },
    "griffin_rumor": {
        "title": "Wings over the mill",
        "region": "White Orchard",
        "banner": "orchard",
        "text": (
            "The trail is feathers, then a horse torn open like a letter, then a peasant who "
            "will only talk if you stand upwind. The griffin has a mate. Of course it has a mate. "
            "Nothing lethal is ever singular.\n\n"
            "Vesemir meets you at the treeline. \"Buckthorn and grapeshot for the flying one. "
            "Don't get poetic.\" Somewhere above, a cry answers, huge and married."
        ),
        "choices": [
            {"label": "Hunt the nest with Vesemir", "next": "griffin_nest"},
            {"label": "Report to the garrison first and get paid twice if you can", "next": "nilf_camp"},
        ],
    },
    "nilf_camp": {
        "title": "Black suns on clean canvas",
        "region": "White Orchard",
        "banner": "orchard",
        "text": (
            "The camp smells of soap and conquest, which is a worse combination than it sounds. "
            "A captain with a fresh shave offers crowns for the griffin and a lecture for free. "
            "He calls the war a reunification. The hanged men by the road call it something else, "
            "quietly.\n\n"
            "He does know one useful thing: an imperial messenger saw a sorceress open a mirror "
            "of light near the ruined tower. \"If she is yours,\" he says, \"collect her before "
            "she becomes a report.\""
        ),
        "set": {"met_nilf": True},
        "items": {"crowns": 20},
        "choices": [
            {"label": "Take the coin and the tower", "next": "griffin_nest", "log": "Nilfgaard will pay for the griffin."},
            {"label": "Refuse the lecture, keep the contract", "next": "griffin_nest", "set": {"snubbed_nilf": True}},
        ],
    },
    "griffin_nest": {
        "title": "The watchtower",
        "region": "White Orchard",
        "banner": "orchard",
        "text": (
            "The nest is a crib made of shields. Eggshells, a child's ribbon that is not a "
            "child's, and the male griffin coming in low because you killed the quiet one first. "
            "Vesemir curses with the fluency of a man who taught other men to curse.\n\n"
            "It is not a duel. It is weather with a beak. You roll under the second pass, silver "
            "finding the join beneath the wing, and the tower fills with the smell of hot coin. "
            "When it falls, the afternoon looks embarrassed.\n\n"
            "In the rubble: a megascope projector, still warm. Lilac and gooseberries, faint "
            "enough that you might be inventing them."
        ),
        "set": {"griffin_dead": True},
        "items": {"crowns": 80, "griffin trophy": 1},
        "log": "The White Orchard griffin is dead. Yennefer left a projector.",
        "choices": [
            {"label": "Fire the projector", "next": "yen_megascope"},
            {"label": "Loot first. Magic can wait a minute.", "next": "yen_megascope", "items": {"crowns": 15}},
        ],
    },
    "yen_megascope": {
        "title": "A window that still remembers her",
        "region": "White Orchard",
        "banner": "orchard",
        "text": (
            "The projection stutters, then settles on Yennefer from the shoulders up, impatient "
            "with being a recording. \"If you're seeing this, you're late,\" she says, which is "
            "how she says hello. Ciri was in Velen. The Ladies of the Wood have their hooks in "
            "the swamps, and a Nilfgaardian baron — not that kind of baron — has been buying "
            "information about an ashen-haired girl.\n\n"
            "The image looks past you, as recordings do. \"Don't be noble at Emhyr. Be useful. "
            "And if you find her before I do, try not to make a speech.\"\n\n"
            "It collapses into sparks. Vesemir grunts. \"Vizima, then. The emperor collects "
            "witchers the way other men collect excuses.\""
        ),
        "set": {"heard_yen": True},
        "choices": [
            {"label": "Claim the bounty, then ride for Vizima", "next": "vizima_gate"},
            {"label": "Settle the well-ghost first. Vizima will keep.", "next": "devil_well"},
        ],
    },
    "vizima_gate": {
        "title": "Vizima, wearing new colors",
        "region": "Vizima",
        "banner": "velen",
        "text": (
            "The capital has been washed and not improved. Black banners, white roses cut back "
            "to the root, clerks who have learned to smile without using their eyes. You are "
            "expected. That is never a comfort.\n\n"
            "A chamberlain informs you that His Imperial Majesty will see you after you have "
            "been cleaned of the road. The bath is excellent. The politics waiting on the other "
            "side of it are not."
        ),
        "choices": [
            {"label": "Go in armored and honest", "next": "vizima_audience", "set": {"honest_emhyr": True}},
            {"label": "Go in polite. Save the honesty.", "next": "vizima_audience", "set": {"polite_emhyr": True}},
        ],
    },
    "vizima_audience": {
        "title": "The man who thinks he is weather",
        "region": "Vizima",
        "banner": "velen",
        "text": (
            "Emhyr var Emreis does not raise his voice. He spends other people's. Ciri, he says, "
            "is his daughter by blood and by a law older than either of you — the Law of Surprise, "
            "paid out once already in a banquet hall that ended in blood and a hedgehog's curse. "
            "He wants her found. He wants her safe. He wants, underneath that, a successor who "
            "can hold a continent together when he is done holding it shut.\n\n"
            "\"The swamps,\" he says. \"Velen. A girl passed through. So did your sorceress. "
            "Bring me news and I will not ask what you almost said just now.\"\n\n"
            "The purse he offers is heavy enough to be an insult. You take it anyway. Pride is "
            "a poor saddlebag."
        ),
        "set": {"met_emhyr": True, "left_vizima": True},
        "items": {"crowns": 200},
        "log": "The emperor hired you to find Ciri. The old books would call that destiny. You call it a contract.",
        "choices": [
            {"label": "Ride for Velen", "next": "velen_inn"},
            {"label": "Ask one sharp question about the Hunt", "next": "emhyr_hunt", "set": {"pressed_emhyr": True}},
        ],
    },
    "emhyr_hunt": {
        "title": "What the emperor will admit",
        "region": "Vizima",
        "banner": "velen",
        "text": (
            "\"The Wild Hunt is not a fairy tale I pay you to mock,\" Emhyr says. The room cools "
            "without anyone opening a window. \"They want what is in her. You want what is left "
            "of her. Do not confuse the two, witcher, or I will find a less sentimental monster "
            "hunter.\"\n\n"
            "He dismisses you with a glance. Outside, the roses have been cut so far back they "
            "look like fists."
        ),
        "choices": [
            {"label": "Velen. Enough thrones for one day.", "next": "velen_inn"},
        ],
    },
}
