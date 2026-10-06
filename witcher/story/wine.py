"""Blood and Wine. Toussaint, the beast, Syanna, Detlaff. Original prose."""

NODES = {
    "beauclair": {
        "title": "Beauclair, which has never heard of mud",
        "region": "Blood and Wine",
        "banner": "wine",
        "rest": True,
        "hub": True,
        "unlock": {"left_vizima": True},
        "text": (
            "Toussaint believes in wine, knights, and the idea that tragedy should wear a ribbon. "
            "Duchess Anna Henrietta wants a beast dead before it eats another tourney. Her "
            "majordomo wants you not to lean on the tapestries. The vineyards want nothing, "
            "which makes them the wisest people here.\n\n"
            "A letter from an old friend in Nilfgaard — Regis, if the handwriting's thirst is "
            "familiar — says the beast is not a fairy tale. Higher vampire. Old debt. Try not "
            "to swing first."
        ),
        "choices": [
            {"label": "Take the duchess's contract", "next": "beast_contract", "log": "Toussaint hired you for a beast that should not exist."},
            {"label": "Find Regis before the court does", "next": "regis"},
        ],
    },
    "regis": {
        "title": "A barber-surgeon with a cellar",
        "region": "Blood and Wine",
        "banner": "wine",
        "text": (
            "Emiel Regis Rohellec Terzieff-Godefroy apologizes for the name and pours something "
            "that is not wine and not blood and not your business. He has been sober, by vampire "
            "standards, and worried, by anyone's. \"Detlaff is my brother in the only way that "
            "counts. Someone is using his heart as a leash. If you kill him on the duchess's "
            "lawn I will be very disappointed, and I hate being disappointed in friends.\""
        ),
        "set": {"met_regis": True},
        "choices": [
            {"label": "Track the beast with him", "next": "beast_contract"},
        ],
    },
    "beast_contract": {
        "title": "Knights, ribbons, and a wrong monster",
        "region": "Blood and Wine",
        "banner": "wine",
        "text": (
            "The killings are precise. The victims share a secret older than the tourney: a "
            "girl exiled, a letter, a childhood bargain. Anna Henrietta will not say her sister's "
            "name. The city says it for her. Syanna. Bandit. Prisoner. The other half of a "
            "story the duchess prefers in tapestry form.\n\n"
            "Detlaff wants Syanna brought to him. He is not negotiating so much as scheduling."
        ),
        "set": {"met_detlaff": True},
        "choices": [
            {"label": "Find Syanna in the prison beyond the river", "next": "syanna"},
        ],
    },
    "syanna": {
        "title": "A sister with a list",
        "region": "Blood and Wine",
        "banner": "wine",
        "text": (
            "Syanna is not sorry in the way the court would like. She is funny, sharp, and "
            "keeping a list of everyone who smiled when she was thrown out of the fairy tale. "
            "Detlaff loves her with the sincerity of a natural disaster. She has been spending "
            "that sincerity on revenge.\n\n"
            "\"You can take me to him,\" she says. \"You can also take me to my sister and see "
            "which of us draws first. I recommend the version with more wine.\" She looks you "
            "over, amused. \"Or we talk on the terrace, and the door closes before the story "
            "gets nosy. I don't mind a witcher. They're used to monsters who talk back.\""
        ),
        "set": {"met_syanna": True},
        "choices": [
            {"label": "The terrace. Fade to black.", "next": "syanna_night", "set": {"syanna_romance": True}, "romance": True},
            {"label": "No. The vampire and the duchess first.", "next": "fables_gate", "set": {"syanna_declined": True}},
            {"label": "Give her the ribbon from the childhood tale", "next": "fables_gate", "set": {"gave_ribbon": True}, "log": "You gave Syanna the ribbon. Fairy tales notice that sort of thing."},
        ],
    },
    "fables_gate": {
        "title": "A land of fables, badly supervised",
        "region": "Blood and Wine",
        "banner": "wine",
        "text": (
            "The only road to a conversation Detlaff will accept runs through a book. You step "
            "into a land of a thousand fables: talking geese, a girl in red who has opinions "
            "about axes, a beanstalk with poor boundaries. Syanna walks it like a woman editing "
            "her own childhood. Regis, if he is with you, refuses to enjoy any of it on principle.\n\n"
            "At the end she can face her sister, or the story can eat one of them. You are the "
            "bookmark."
        ),
        "choices": [
            {"label": "Bring the sisters to the same table", "next": "sisters"},
            {"label": "Hand Syanna to Detlaff and end it", "next": "detlaff_meets"},
        ],
    },
    "sisters": {
        "title": "Anna Henrietta, without the tapestry",
        "region": "Blood and Wine",
        "banner": "wine",
        "text": (
            "The duchess wants an apology that doubles as a confession. Syanna wants a childhood "
            "returned in coin. Between them is a playground and a knife. If you found the ribbon "
            "and used it, the oldest magic in the room is a child's promise, not a court sentence. "
            "If you didn't, the sentence arrives anyway."
        ),
        "choices": [
            {"label": "Force the truth. Keep both breathing.", "next": "ending_beauclair", "requires": {"gave_ribbon": True}, "set": {"sisters_live": True}},
            {"label": "Side with the duchess. Syanna answers for the dead.", "next": "ending_syanna_dead", "set": {"syanna_executed": True}},
            {"label": "This cannot be talked out. Detlaff is still coming.", "next": "detlaff_meets"},
        ],
    },
    "detlaff_meets": {
        "title": "Night of long fangs",
        "region": "Blood and Wine",
        "banner": "wine",
        "text": (
            "Beauclair learns what a higher vampire does when a love letter turns out to be a "
            "leash. The sky fills with things that used to be bats and have been promoted. Regis "
            "stands with you because friendship, in his case, is a combat style. Detlaff will "
            "not be argued out of a broken vow. He can be stopped. Stopping a higher vampire is "
            "a sentence you serve together."
        ),
        "choices": [
            {"label": "Fight him. Regis finishes what you start.", "next": "ending_detlaff", "set": {"detlaff_dead": True}},
            {"label": "Try to show him Syanna's lie before the city burns", "next": "ending_beauclair", "requires": {"gave_ribbon": True, "met_regis": True}},
        ],
    },
    "ending_beauclair": {
        "title": "Two sisters and a vineyard",
        "region": "Blood and Wine",
        "banner": "ending",
        "ending": True,
        "text": (
            "Anna Henrietta does not thank you in public. In private she pours the good year "
            "and asks you to stay for a winter, which in Toussaint means until the story gets "
            "bored. Syanna lives, supervised by a sister and a ribbon. Detlaff is gone or "
            "chastened, depending on the blood in the plaza. Regis raises a glass of something "
            "you don't inspect.\n\n"
            "There is an estate with your name on a gate, if you want it. You might.\n\n"
            "_Blood and Wine: Beauclair stands. So do the people you refused to spend._"
        ),
        "choices": [],
    },
    "ending_syanna_dead": {
        "title": "A duchess with one sister",
        "region": "Blood and Wine",
        "banner": "ending",
        "ending": True,
        "text": (
            "The execution is legal and looks like a mistake the moment it is over. Detlaff "
            "feels the leash snap and comes anyway. You and Regis put him in the ground at a "
            "cost the tourney poet will sand down. Anna Henrietta does not speak to you at the "
            "gate. The vineyard offer does not arrive.\n\n"
            "_Blood and Wine: the beast is dead. So is the happier ending._"
        ),
        "choices": [],
    },
    "ending_detlaff": {
        "title": "What remains of a brother",
        "region": "Blood and Wine",
        "banner": "ending",
        "ending": True,
        "text": (
            "Regis does the last part because only he can. He does not forgive you and does not "
            "leave you. That is the shape of this friendship. Beauclair rebuilds the district "
            "Detlaff emptied and names a wine after the victory, which Regis refuses to drink.\n\n"
            "You wash the silver. The duchy pretends the week was a pageant. It wasn't.\n\n"
            "_Blood and Wine: Detlaff falls. The city keeps the scar._"
        ),
        "choices": [],
    },
}
