"""Velen: the Baron, the Crones, Keira, the trail to Uma. Original prose."""

NODES = {
    "velen_inn": {
        "title": "The Inn at the Crossroads",
        "region": "Velen",
        "banner": "velen",
        "rest": True,
        "hub": True,
        "unlock": {"left_vizima": True},
        "text": (
            "Velen is what a war looks like after the interesting part leaves. Hanged men season "
            "the trees. The innkeeper waters the beer and will not water down the warning: "
            "Crow's Perch belongs to Phillip Strenger, the Bloody Baron, and the Baron belongs "
            "to whatever he drank last. A girl with ashen hair? He laughs once, badly.\n\n"
            "\"Everybody's looking for somebody. The Ladies look back.\"\n\n"
            "Your medallion ticks when the door opens, then decides it was only the wind. "
            "The wind in Velen has opinions."
        ),
        "choices": [
            {"label": "Ride to Crow's Perch", "next": "baron_hall"},
            {"label": "Ask about the Ladies of the Wood", "next": "crones_rumor"},
            {"label": "Take a swamp contract before politics", "next": "shrieker_board"},
            {"label": "A Cat-school rumor on the north road", "next": "cat_school"},
            {"label": "See if the sergeant's wife still haunts Fyke Isle", "next": "fyke_dock", "requires": {"heard_fyke": True}},
        ],
    },
    "crones_rumor": {
        "title": "Whispered, because names are edible",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "They are called the Ladies, and also Weavess, Brewess, and the one who cooks. "
            "Peasants leave ears of grain and unwanted children at the shrines. In return the "
            "swamp sometimes does not eat the rest of the family. An old woman by the fire says "
            "a witcher should know better than to pick between monsters and gods.\n\n"
            "\"Same teeth,\" she says. \"Better hats on the gods.\""
        ),
        "set": {"heard_crones": True},
        "choices": [
            {"label": "The Baron will have a map, if he has anything", "next": "baron_hall"},
            {"label": "Back to the inn fire", "next": "velen_inn"},
        ],
    },
    "baron_hall": {
        "title": "Crow's Perch",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "Phillip Strenger is a large man trying to occupy a small redemption. He pours "
            "without asking and talks about his wife the way some men talk about a war they "
            "started and then mislaid. Anna is gone. His daughter Tamara is gone. A girl matching "
            "Ciri's description slept in the stables and left toward the orphans and the bog.\n\n"
            "\"Help me find my Anna,\" he says, \"and I'll open every door I still own. There's "
            "a thing in the room upstairs. It cries with my dead baby's voice. I haven't opened "
            "that door sober.\""
        ),
        "set": {"met_baron": True},
        "log": "The Baron trades Ciri's trail for his family's.",
        "choices": [
            {"label": "Deal with the thing upstairs", "next": "botchling"},
            {"label": "Refuse the haunting. Demand the trail.", "next": "baron_refused", "set": {"baron_cold": True}},
        ],
    },
    "baron_refused": {
        "title": "A man who expected to be obeyed",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The Baron's smile leaves before the rest of his face. \"Witchers. Always a price, "
            "never a favor.\" He still talks. Pride is not the same as silence. Ciri went to "
            "the orphans' croft, then the bog. His own mess, he says, can rot with him.\n\n"
            "You leave him with the bottle. Some contracts are kinder declined. This one will "
            "not feel kind later."
        ),
        "choices": [
            {"label": "Follow Ciri's trail toward Downwarren", "next": "downwarren"},
            {"label": "Change your mind and open the upstairs door", "next": "botchling"},
        ],
    },
    "botchling": {
        "title": "What a buried name becomes",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "It is small, and that is the worst part. A botchling is a child who was refused "
            "the world and grew teeth out of spite. The Baron looks at it as if looking might "
            "still count as fathering.\n\n"
            "You can kill it clean, under the floorboards' dark, or drag the Baron through the "
            "rite: name the child, carry him to the crossroads, bleed a little, and give the "
            "thing a grave. One road is shorter. The other leaves a lubberkin that remembers "
            "how to point."
        ),
        "choices": [
            {"label": "Give the child a name and a burial", "next": "family_grave", "set": {"botchling_saved": True}, "log": "The Baron named his son. The lubberkin pointed toward the bog."},
            {"label": "End it. The Baron has enough ghosts.", "next": "botchling_dead", "set": {"botchling_killed": True}},
        ],
    },
    "botchling_dead": {
        "title": "A short mercy",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "Silver, once, and the crying stops. The Baron thanks you with a voice that has "
            "nowhere to go. He still knows the croft. He does not know how to stand in the room "
            "afterward, so he doesn't. You take the trail notes from the table and leave him "
            "the bottle, which is not kindness and not cruelty. It is what he would have done "
            "anyway."
        ),
        "choices": [
            {"label": "Downwarren, and the Ladies' country", "next": "downwarren"},
        ],
    },
    "family_grave": {
        "title": "A procession nobody applauds",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "You walk at night because shame prefers an audience of owls. The Baron carries the "
            "bundle. Things come out of the rye to contest the point. He bleeds and does not "
            "put the child down. At the grave marker he says a name he should have said months "
            "ago. The lubberkin unfolds into something that can forgive, or at least point.\n\n"
            "It points at the orphan croft, then at the heart of the swamp. \"Anna,\" the Baron "
            "says, hoarse. \"And your girl went the same way. Everybody goes the same way here.\""
        ),
        "choices": [
            {"label": "Follow the pointing hand", "next": "downwarren"},
        ],
    },
    "downwarren": {
        "title": "Downwarren keeps its head down",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The village has given so many children to the Ladies that the dogs don't bark at "
            "strangers anymore, in case the strangers are owed. The ealdorman tells you the "
            "orphan girl — ashen hair, scar at the cheek, a way of looking through people — "
            "broke a shrine and ran. The trail goes to the Whispering Hillock, where an older "
            "thing than the Crones is trapped in a tree, talking in roots.\n\n"
            "\"Free it and the Ladies go hungry,\" he says. \"Leave it and they go on eating. "
            "I'm not asking. I'm explaining the menu.\""
        ),
        "set": {"heard_fyke": True},
        "choices": [
            {"label": "Speak to the spirit in the tree", "next": "spirit_free"},
            {"label": "Go to the Crones as a guest, not a thief", "next": "crones_deal"},
            {"label": "Detour to Fyke Isle. The mice story smells like a contract.", "next": "fyke_dock"},
        ],
    },
    "spirit_free": {
        "title": "The Whispering Hillock",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The spirit does not pretend to be good. It pretends to be older, which in a swamp "
            "is almost the same sales pitch. Free me, it says, and the children of Downwarren "
            "leave the oven. The Crones will be angry. Angry gods are still gods. A witcher "
            "once wrote that evil is evil, lesser or otherwise, and then lived with the sentence.\n\n"
            "You can cut the roots and let it out. You can burn the heartwood and go to the "
            "Ladies with a gift of obedience. Neither feels like a song."
        ),
        "choices": [
            {"label": "Free the spirit. Get the children out.", "next": "spirit_out", "set": {"spirit_freed": True, "crones_angry": True}, "log": "You freed the Hillock spirit. The Crones will want a word."},
            {"label": "Destroy it and deal with the Ladies", "next": "crones_deal", "set": {"spirit_killed": True}},
        ],
    },
    "spirit_out": {
        "title": "A bargain with bark",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The tree splits like a smile. Something tall and antlered thanks you without "
            "gratitude and is gone, taking a wind of orphans with it — or so the tracks say. "
            "Downwarren will call this a theft. The children will call it Tuesday in a new "
            "county.\n\n"
            "The Crones' shrine has been kicked over. Under it, a wooden toy and a lock of "
            "ashen hair. Ciri was here. She was not polite either."
        ),
        "choices": [
            {"label": "Face the Ladies anyway", "next": "crones_deal"},
            {"label": "Find the sorceress in the tower west of the bog", "next": "keira_tower"},
        ],
    },
    "crones_deal": {
        "title": "Ladies, if one insists",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "They receive you in a hut that is larger inside than a lie. Brewess stirs. Weavess "
            "threads hair that is not hers. The third smiles with too many dinners behind it. "
            "They know Ciri. They know Anna, who is a lump of grief and curse in the next room, "
            "working the loom of a woman who ran out of choices.\n\n"
            "\"The girl broke our toy and fled toward Novigrad,\" the smiling one says. \"Your "
            "baroness can leave if you do us a small eating. Or she can stay beautiful and "
            "useful.\" Anna's eyes are the only honest things in the hut."
        ),
        "set": {"met_crones": True},
        "choices": [
            {"label": "Take Anna. Pay whatever they ask later.", "next": "anna_free", "set": {"anna_saved": True, "crones_bargain": True}, "log": "Anna leaves the Crones alive, and cursed in a quieter way."},
            {"label": "No deals. Steel, and then fire.", "next": "anna_lost", "set": {"crones_fought": True, "anna_dead": True}},
        ],
    },
    "anna_free": {
        "title": "A wife returned, not restored",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The Baron weeps in the practical way of men who have been cruel and are briefly "
            "allowed to stop. Anna does not forgive him. She does let him put a cloak on her. "
            "That is more than the swamp offered. Tamara's trail points to a chapel and a hard "
            "faith; you leave that door for the family that broke it.\n\n"
            "Ciri's road leaves the bog toward the free city. On the way, a tower with too much "
            "light in it. Keira Metz, if the gossip is worth the breath."
        ),
        "choices": [
            {"label": "Visit Keira Metz", "next": "keira_tower"},
            {"label": "Novigrad can wait on a mage. Ride.", "next": "uma_hint"},
        ],
    },
    "anna_lost": {
        "title": "No lesser evil on the menu",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The hut burns. So does the loom. You get out with a singed eyebrow and the knowledge "
            "that Anna died between one curse and the next, looking at you as if you were another "
            "weather. The Baron will hear. He will not be a better man for the hearing.\n\n"
            "Ciri's wooden swallow is in your pocket, snapped at the wing. Novigrad. Always "
            "Novigrad when a child runs out of forest."
        ),
        "choices": [
            {"label": "The tower light on the way out", "next": "keira_tower"},
            {"label": "Skip the mage. Find the city.", "next": "uma_hint"},
        ],
    },
    "keira_tower": {
        "title": "Fyke's other tenant",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "Keira Metz has set up in a tower that still smells of mice and old love. She is "
            "beautiful the way a scalpel is beautiful, and she wants a witcher for the things "
            "in the cellar, plus a conversation about a plague note she absolutely should not "
            "sell to Radovid.\n\n"
            "\"Stay after,\" she says, lightly, as if asking you to pass the salt. \"The swamp "
            "is dull and you are only mostly.\" Ciri, she adds, went north. A goat-thing of a "
            "man was asking after an elf's curse. She did not like his smile."
        ),
        "set": {"met_keira": True, "heard_uma": True},
        "choices": [
            {"label": "Clear her cellar, then hear the offer", "next": "keira_offer"},
            {"label": "Take the Uma lead and leave the flirtation", "next": "uma_hint", "set": {"keira_declined": True}},
        ],
    },
    "keira_offer": {
        "title": "Salt, steel, and a closed door",
        "region": "Velen",
        "banner": "romance",
        "text": (
            "The cellar is a wraith and a lesson. After, Keira pours something that is not swamp "
            "water and sits on the table like a woman who has decided the evening has a second "
            "plot. She talks about Radovid's fires, about notes that could buy her a pardon, "
            "about being tired of running in heels not made for running.\n\n"
            "You can stay. The door will shut, and the scene will fade to black. You can take "
            "the notes instead and send her toward Kaer Morhen, where the fires are only hearths. "
            "One of those is kinder."
        ),
        "choices": [
            {"label": "Stay. The door shuts. Fade to black.", "next": "keira_night", "set": {"keira_romance": True}, "romance": True},
            {"label": "Take the notes. Send her to the keep.", "next": "keira_safe", "set": {"keira_to_morhen": True, "keira_notes": True}},
            {"label": "Take the notes and let her go to Radovid", "next": "uma_hint", "set": {"keira_radovid": True, "keira_notes": True}, "log": "Keira left with a dangerous idea and Radovid's name in her mouth."},
        ],
    },
    "keira_safe": {
        "title": "A mage aimed at a hearth",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "Keira laughs when you tell her to go to Kaer Morhen. Then she stops laughing, which "
            "is how you know she heard you. \"Wolf school hospitality. I'll bring wine so it "
            "counts as a visit.\" She burns the worst page of the notes and pockets the rest. "
            "\"Find your girl, Geralt. Try not to collect any more cursed families on the way.\""
        ),
        "log": "Keira rides for Kaer Morhen instead of a king's fire.",
        "choices": [
            {"label": "After the goat-cursed man", "next": "uma_hint"},
        ],
    },
    "uma_hint": {
        "title": "A curse with horns",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The trail ends, for now, at a name people spit: Uma. An ugliness wearing a man's "
            "shape, kept by the Baron or by whoever paid the Baron's debts. Elven curse-work, "
            "Keira said, or the inn said, or the swamp said. Under it, maybe a sage who actually "
            "saw Ciri.\n\n"
            "Novigrad has the mages, the spies, and the poet who never met a secret he could "
            "hold. Skellige has Yennefer, if the storms haven't argued her into wreckage. "
            "You cannot be both places. You can be one, then the other."
        ),
        "set": {"velen_done": True, "uma_rumor": True},
        "log": "Ciri's trail leaves Velen. An elven curse named Uma waits somewhere behind a baron.",
        "choices": [
            {"label": "Novigrad, and Dandelion's latest disaster", "next": "novigrad_gate"},
            {"label": "Skellige, if Yen is really there", "next": "skellige_dock"},
            {"label": "Rest at the inn before the road", "next": "velen_inn"},
        ],
    },
}
