"""Kaer Morhen, the battle, Ciri's ending forks. Original prose."""

NODES = {
    "kaer_morhen": {
        "title": "The wolf keep, pretending not to hope",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "rest": True,
        "hub": True,
        "unlock": {"uma_in_hand": True},
        "text": (
            "The keep is colder than memory and warmer than you admit. Vesemir pretends the "
            "gate needed fixing anyway. Lambert pretends he is not glad. Eskel pretends nothing, "
            "which is why he is the most honest of you. If Keira came, she is already criticizing "
            "the wine. If she didn't, nobody mentions the empty chair.\n\n"
            "Uma sits by the fire and laughs at a joke only the curse understands. Yennefer — "
            "if she sailed with you — taps the laboratory key against her lip. \"Tomorrow we "
            "peel him. Tonight you can be a person. Don't waste it on a speech.\""
        ),
        "choices": [
            {"label": "The laboratory. Lift the curse.", "next": "uma_lift"},
            {"label": "Walk the battlements with Vesemir", "next": "vesemir_walk"},
            {"label": "If both sorceresses are in your story, the hall has a third chair", "next": "both_fail", "requires": {"triss_romance": True, "yen_romance": True}},
        ],
    },
    "vesemir_walk": {
        "title": "A teacher counting wolves",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "Vesemir talks about the Trial, the dead boys, the way the world improved itself "
            "by forgetting witchers until it needed them. He stops at the notch in the wall "
            "where you once threw a knife and missed. \"If the girl comes back, don't make her "
            "a soldier to soothe yourself. The books you pretend not to read are clear on that. "
            "Surprise children aren't weapons. They're the bill.\""
        ),
        "choices": [
            {"label": "Down to the laboratory", "next": "uma_lift"},
        ],
    },
    "uma_lift": {
        "title": "Under the ugly, an elf",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "The rite is ugly. Uma screams in two voices. Then the curse sloughs off like a "
            "bad joke told too long, and Avallac'h sits on the stone, elven, exhausted, and "
            "annoyed to be saved by a school he regards as a blunt instrument.\n\n"
            "\"Ciri lives,\" he says. \"The Hunt lives louder. She went to the Isle of Mists "
            "because the mists do not take navigation from the kind of riders who have no "
            "names. I can open the way. You will not enjoy the price of keeping her.\""
        ),
        "set": {"avallach_free": True},
        "log": "Uma was Avallac'h. Ciri waits beyond the Isle of Mists.",
        "choices": [
            {"label": "Prepare the keep. They will come here after.", "next": "battle_prep"},
            {"label": "Sail for the mists at once", "next": "isle_mists"},
        ],
    },
    "isle_mists": {
        "title": "Where maps give up",
        "region": "Skellige",
        "banner": "skellige",
        "text": (
            "The mists take the ship and give it back smaller. Ciri is on the shore with her "
            "hair hacked by weather and her smile older than the last time you were allowed to "
            "see it. She hits your chest with both hands, not gently.\n\n"
            "\"You're late,\" she says, and then, smaller, \"I knew you'd come anyway.\" "
            "Avallac'h looks away, which is as close as he gets to letting a moment live. "
            "The Hunt's horn sounds, far and too close. The keep is the only door left."
        ),
        "set": {"ciri_found": True},
        "log": "Ciri is found. The Hunt is already on the water.",
        "choices": [
            {"label": "Bring her home to Kaer Morhen", "next": "battle_prep"},
        ],
    },
    "battle_prep": {
        "title": "Before the horn",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "You have a night. Ciri sits on the table, boots muddy, stealing Lambert's vodka "
            "and telling the story wrong on purpose so Eskel will correct it. This is the part "
            "the emperors never buy. How you are with her now changes the girl who walks into "
            "the last fog.\n\n"
            "In the yard, snow starts, absurd for the season, as if the keep remembered a "
            "child who used to demand a fight."
        ),
        "set": {"at_keep_with_ciri": True},
        "choices": [
            {"label": "Snowball fight. Let her win, or don't.", "next": "ciri_snow", "set": {"ciri_joy": True}, "log": "You played in the snow with Ciri like a man who intends to keep her."},
            {"label": "Take her to pay respects at the old graves", "next": "ciri_grave", "set": {"ciri_grief_shared": True}},
            {"label": "Drink instead. Keep it light.", "next": "ciri_drink", "set": {"ciri_kept_distance": True}},
        ],
    },
    "ciri_snow": {
        "title": "A war postponed by snow",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "She cheats. You cheat. Vesemir pretends to disapprove and then takes a shot at "
            "Lambert, who deserved it on general principle. For ten minutes nobody is a weapon. "
            "Ciri's laugh is the same one from when she was small enough to hide behind Roach. "
            "You do not say this. She hears it anyway."
        ),
        "choices": [
            {"label": "The laboratory door, later, when she rages", "next": "ciri_lab"},
            {"label": "Hold the quiet. Don't follow her anger.", "next": "hunt_arrives", "set": {"ciri_trusted": True}},
        ],
    },
    "ciri_grave": {
        "title": "Names under snow",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "You stand with her where the school keeps its dead. She asks if you ever wanted "
            "a different life. You tell the truth: you wanted this one, with fewer pyres. She "
            "leans on you the way she did before the Hunt taught her not to. Trust, in this "
            "family, is a series of small permissions."
        ),
        "choices": [
            {"label": "When she smashes the laboratory, go after her", "next": "ciri_lab"},
            {"label": "Let her smash it. Wait outside.", "next": "hunt_arrives", "set": {"ciri_trusted": True}},
        ],
    },
    "ciri_drink": {
        "title": "Almost a conversation",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "The vodka is fine. The distance is not. Ciri watches you choose the easy sentence "
            "and files it away with the other times adults were careful instead of present. "
            "She still smiles. Ciri has always been better at mercy than the people around her."
        ),
        "choices": [
            {"label": "Follow her when the laboratory breaks", "next": "ciri_lab"},
            {"label": "Give her the room", "next": "hunt_arrives"},
        ],
    },
    "ciri_lab": {
        "title": "The wrecked laboratory",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "She has turned Avallac'h's instruments into a moral argument. You can scold her "
            "like a ward, or you can sit in the wreckage and let her be angry that the world "
            "wants her blood more than her name. One of those teaches her she is a problem. "
            "The other teaches her she is allowed to refuse."
        ),
        "choices": [
            {"label": "Sit down. Anger isn't disobedience.", "next": "hunt_arrives", "set": {"ciri_trusted": True}, "log": "You sided with Ciri against the elven plan."},
            {"label": "Tell her to control herself. The rite matters.", "next": "hunt_arrives", "set": {"ciri_scolded": True}, "log": "You scolded Ciri in the laboratory."},
        ],
    },
    "hunt_arrives": {
        "title": "The Wild Hunt comes to the door",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "They arrive like winter that learned to ride. The battle is noise, ice, and "
            "Vesemir in the place he was always going to stand: between Ciri and a king with "
            "no face worth remembering. He dies there. Not poetically. Practically. A teacher "
            "finishing a lesson with his body.\n\n"
            "Ciri screams and the courtyard becomes a wound in the world. The Hunt breaks. "
            "What remains is a girl looking at you to see what you do with her grief."
        ),
        "set": {"vesemir_dead": True},
        "log": "Vesemir fell at Kaer Morhen. The Hunt broke on Ciri's scream.",
        "choices": [
            {"label": "Hold her. Grief first.", "next": "after_vesemir", "set": {"ciri_held": True}},
            {"label": "Point her at revenge. The Crones. Imlerith.", "next": "after_vesemir", "set": {"ciri_aimed": True}},
        ],
    },
    "after_vesemir": {
        "title": "Ash on the battlements",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "You bury him with the others. Lambert does not speak. Eskel does, briefly, which "
            "is worse. Ciri stands until the song ends and then asks, very calmly, where the "
            "Crones went. Everyone knows. Bald Mountain. A sabbath. Imlerith, who dealt the blow, "
            "will be a guest.\n\n"
            "After that, Avallac'h says, the White Frost, and a tower that is not on any map "
            "a king owns. Emhyr's letter arrives anyway, because emperors believe timing is a "
            "virtue."
        ),
        "choices": [
            {"label": "Bald Mountain", "next": "bald_mountain"},
            {"label": "Read Emhyr's letter with Ciri", "next": "emhyr_letter"},
        ],
    },
    "emhyr_letter": {
        "title": "A father on paper",
        "region": "Kaer Morhen",
        "banner": "morhen",
        "text": (
            "He offers a crown and a pardon and the word daughter, in that order. Ciri reads "
            "it twice. \"If I go, it's because I choose the living over the pyre. Not because "
            "he wrote neatly.\" She looks at you. This is one of the hinges. Encouraging the "
            "throne is not the same as selling her. Refusing it for her is its own theft."
        ),
        "choices": [
            {"label": "Tell her she would be a good empress, if she wants it", "next": "bald_mountain", "set": {"urged_empress": True}},
            {"label": "Tell her the throne is a cage with better curtains", "next": "bald_mountain", "set": {"urged_free": True}},
            {"label": "Say nothing. It's her letter.", "next": "bald_mountain", "set": {"urged_nothing": True}},
        ],
    },
    "bald_mountain": {
        "title": "Bald Mountain sabbath",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The Crones feast under a sky that has given up. Imlerith wants a duel and gets "
            "one. He is a wall with a weapon. You take the wall apart. Ciri takes the Ladies, "
            "and the sound they make leaving the world is like a pot boiling dry.\n\n"
            "If Anna lived, this is where the curse finishes its arithmetic. If she didn't, "
            "the Baron has already done something unforgivable to a tree. You do not stay to "
            "watch either ending. Ciri is already looking north, toward a sunstone and a father "
            "she has not agreed to keep."
        ),
        "set": {"crones_done": True},
        "log": "Imlerith is dead. The Crones' sabbath is ash.",
        "choices": [
            {"label": "Novigrad or Skellige — the sunstone", "next": "sunstone"},
            {"label": "If you never settled the bridge, the North is still on fire", "next": "sunstone"},
        ],
    },
    "sunstone": {
        "title": "A stone that remembers ships",
        "region": "Skellige",
        "banner": "skellige",
        "text": (
            "Avallac'h's sunstone opens a path the Hunt cannot quite steal. Ciri stands at the "
            "edge of the light with her sword drawn and her mind elsewhere. This is the last "
            "ordinary talk. She asks if you are proud of her. She asks if you will lie to Emhyr. "
            "She asks if Vesemir was afraid. You answer two of the three."
        ),
        "choices": [
            {"label": "\"I'm proud of you. Go. I'll handle the emperor.\"", "next": "tedd", "set": {"ciri_proud": True, "will_lie_emhyr": True}},
            {"label": "\"He deserves the truth. You'd be greater than he is.\"", "next": "tedd", "set": {"ciri_proud": True, "will_tell_emhyr": True}, "requires": {"urged_empress": True}},
            {"label": "Hesitate. Talk about the frost instead of her.", "next": "tedd", "set": {"ciri_doubted": True}},
        ],
    },
    "tedd": {
        "title": "Tedd Deireadh, the end of the end",
        "region": "The White Frost",
        "banner": "ending",
        "text": (
            "The world thins. Avallac'h's plan wants Ciri as a key. She looks back once. "
            "Whether she walks into that light as a woman choosing, or as a girl pushed, was "
            "decided in snow and wreckage and the sentence you did or did not say.\n\n"
            "You fight the last of the Hunt because that is the part you are for. The rest is hers."
        ),
        "choices": [
            {"label": "Wait for what comes back", "next": "ending_resolve"},
        ],
    },
    "ending_resolve": {
        "title": "What the road pays",
        "region": "Epilogue",
        "banner": "ending",
        "text": (
            "Snow. A long time. Then a shape, or a letter, or a sword you had made for hands "
            "slightly smaller than yours. The ending depends on whether Ciri trusted you, "
            "whether you sold her to a crown, and who is still waiting when the inn door opens."
        ),
        "choices": [
            {"label": "If she trusted you and you kept the throne off her back", "next": "ending_witcher", "requires": {"ciri_trusted": True, "not:urged_empress": True, "not:ciri_doubted": True}},
            {"label": "If you aimed her at the empire and told Emhyr the truth", "next": "ending_empress", "requires": {"urged_empress": True, "will_tell_emhyr": True, "ciri_trusted": True}},
            {"label": "If the doubt won", "next": "ending_ash", "requires": {"ciri_doubted": True}},
            {"label": "See who shares your road after", "next": "ending_company"},
            {"label": "Take the road your choices already bought", "next": "ending_road"},
        ],
    },
    "ending_witcher": {
        "title": "A silver sword, a bad inn, a daughter",
        "region": "Epilogue",
        "banner": "ending",
        "ending": True,
        "text": (
            "You lie to the emperor. It is the cleanest sentence you have spoken in his presence. "
            "Ciri meets you in White Orchard under a sign that still creaks. You give her a "
            "witcher's blade, not as a chain, as a tool she can also put down. She complains "
            "about the balance so she does not have to say anything softer.\n\n"
            "The Hunt is a story now. Vesemir is a name you both say correctly. The road is "
            "still long, and for once it is not only yours.\n\n"
            "_Ending: Ciri walks the Path. The emperor has a grave with no body in it._"
        ),
        "choices": [],
    },
    "ending_empress": {
        "title": "A crown she picked up herself",
        "region": "Epilogue",
        "banner": "ending",
        "ending": True,
        "text": (
            "Emhyr gets his daughter and, annoyingly, a better heir than he deserves. Ciri "
            "takes the throne with her jaw set and your lessons misquoted into policy. You bow "
            "just enough to be rude. She does not cry. She does send the guards out.\n\n"
            "\"If I become him,\" she says, \"come and steal me back.\" You say you will. "
            "You both know the palace has fewer doors than a swamp.\n\n"
            "_Ending: Ciri wears the empire. You keep a horse at the gate anyway._"
        ),
        "choices": [],
    },
    "ending_ash": {
        "title": "A sword left in the snow",
        "region": "Epilogue",
        "banner": "ending",
        "ending": True,
        "text": (
            "She does not come back. You tell yourself a different story for three villages "
            "and then stop, because lying to peasants is one thing and lying to Roach is beneath "
            "you. The medallion is only metal. A hut on the edge of a swamp still has a swallow "
            "potion and a contract nailed to the post. You take the contract.\n\n"
            "Somewhere a frost that is not weather finishes a sentence you were in too much "
            "of a hurry to hear.\n\n"
            "_Ending: Ciri is gone. The Path continues, quieter._"
        ),
        "choices": [],
    },
    "ending_road": {
        "title": "The bill, paid in weather",
        "region": "Epilogue",
        "banner": "ending",
        "ending": True,
        "text": (
            "White Orchard looks smaller on the way back. The inn sign still creaks. Whatever "
            "you told the emperor, whatever you did with the snow and the laboratory and the "
            "two women who know you too well, the Path does what it always does: it continues "
            "in the shape of the last true thing you said.\n\n"
            "Ciri's name is a coin you can still spend honestly. Spend it.\n\n"
            "_Ending: the campaign closes on the road you actually walked._"
        ),
        "choices": [],
    },
    "ending_company": {
        "title": "Who is left at the table",
        "region": "Epilogue",
        "banner": "romance",
        "text": (
            "The war has opinions about your personal life. Triss writes from Kovir, or doesn't. "
            "Yennefer is on the road ahead, or she isn't. Trying to keep both was a young man's "
            "plan, and you are not young."
        ),
        "choices": [
            {"label": "Yennefer, if the wish was a choice this time", "next": "ending_yen", "requires": {"yen_romance": True, "not:triss_romance": True}},
            {"label": "Triss, if she stayed for you and not the ship", "next": "ending_triss", "requires": {"triss_romance": True, "not:yen_romance": True}},
            {"label": "Neither. The table is a table.", "next": "ending_alone", "requires": {"not:yen_romance": True, "not:triss_romance": True}},
            {"label": "You tried for both", "next": "ending_both", "requires": {"yen_romance": True, "triss_romance": True}},
        ],
    },
    "ending_yen": {
        "title": "A vineyard nobody assigned you",
        "region": "Epilogue",
        "banner": "ending",
        "ending": True,
        "text": (
            "Yennefer claims she picked the house for the light. You claim you picked the horse "
            "for the road. Neither of you is fooled. The djinn's wish is a story you tell at "
            "other people's weddings, edited for company. Some nights she still says your name "
            "like an argument she intends to win slowly.\n\n"
            "_Ending: Geralt and Yennefer, retired only in the way storms retire._"
        ),
        "choices": [],
    },
    "ending_triss": {
        "title": "Kovir, and a woman who stayed",
        "region": "Epilogue",
        "banner": "ending",
        "ending": True,
        "text": (
            "Kovir is cold and well governed and slightly too pleased with itself. Triss meets "
            "you at the dock with ink on her wrist and a smile she does not spend on councils. "
            "You are not a secret. You are a complication she has decided to keep.\n\n"
            "_Ending: Geralt and Triss. The ship sailed, and so did you._"
        ),
        "choices": [],
    },
    "ending_alone": {
        "title": "A wide road, honestly empty",
        "region": "Epilogue",
        "banner": "ending",
        "ending": True,
        "text": (
            "No one waits in the doorway. That is not a tragedy unless you insist. Roach does "
            "not care about epilogues. There is a contract on the board and a bard somewhere "
            "getting your armor wrong. You sleep. You wake. The Path is still a path.\n\n"
            "_Ending: no romance. Plenty of road._"
        ),
        "choices": [],
    },
    "ending_both": {
        "title": "A reunion with too many chairs",
        "region": "Epilogue",
        "banner": "ending",
        "ending": True,
        "text": (
            "They let you arrive first. That should have been the warning. Triss pours. Yen "
            "does not sit. The conversation is short, accurate, and conducted at a volume that "
            "respects the furniture. You leave single. Dandelion, somewhere, writes the polite "
            "version and hates it.\n\n"
            "_Ending: both romances collapse. You keep the lesson._"
        ),
        "choices": [],
    },
}
